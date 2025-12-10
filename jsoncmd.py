#!/usr/bin/env python3
# jsoncmd.py - improved: supports filter syntax personagens[?prop=="value"]
# Added: support for "/?" to display help (Windows-style)

import sys, json, argparse, base64, os, re

EXIT_OK = 0
EXIT_DIFF = 1
EXIT_USAGE = 2
EXIT_NOFILE = 3
EXIT_PARSE_ERROR = 4
EXIT_B64_ERROR = 5

def canonical_string(val):
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    try:
        return json.dumps(val, ensure_ascii=False, separators=(',',':'))
    except:
        return str(val)

def decode_literal(tok):
    if tok is None:
        return ""
    if tok.lower().startswith("b64:"):
        b64 = tok[4:]
        try:
            return base64.b64decode(b64).decode('utf-8')
        except Exception:
            print("Erro ao decodificar Base64", file=sys.stderr)
            sys.exit(EXIT_B64_ERROR)
    return tok

def split_path(path):
    # split by dot but preserve bracketed segments
    if not path:
        return []
    parts = []
    cur = ''
    i = 0
    while i < len(path):
        c = path[i]
        if c == '.':
            parts.append(cur)
            cur = ''
            i += 1
            continue
        if c == '[':
            # copy until matching ]
            start = i
            depth = 0
            while i < len(path):
                if path[i] == '[':
                    depth += 1
                elif path[i] == ']':
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            cur += path[start:i]
            continue
        cur += c
        i += 1
    if cur != '':
        parts.append(cur)
    return parts

def matches_filter(item, cond):
    # cond example: nome=="Goku"  or nome=='Goku'
    m = re.match(r'^\s*([^\s=<>!]+)\s*==\s*(?:"([^"]*)"|\'([^\']*)\'|([^"\']\S*))\s*$', cond)
    if not m:
        return False
    key = m.group(1)
    val = m.group(2) if m.group(2) is not None else (m.group(3) if m.group(3) is not None else (m.group(4) or ''))
    # get item[key]
    v = None
    if isinstance(item, dict):
        v = item.get(key)
    else:
        try:
            v = item[key]
        except Exception:
            v = None
    if v is None:
        return False
    # compare case-insensitive for strings; otherwise canonical compare
    if isinstance(v, str):
        return v.lower() == val.lower()
    else:
        return canonical_string(v) == canonical_string(val)

def get_json_value(obj, path):
    if not path:
        return None
    parts = split_path(path)
    current_values = [obj]
    for part in parts:
        next_values = []
        # handle filter pattern like prop[?cond] or name[index] or prop[] or *
        # Detect "prop[?cond]" or "[?cond]" or "prop[index]" or "prop[]"
        m_filter = re.match(r'^(.*?)\[\?(.*)\]$', part)
        m_index = re.match(r'^(.*?)(\[(\d+)\])$', part)
        m_expand = re.match(r'^(.*?)\[\]$', part)
        for cur in current_values:
            if cur is None:
                continue
            # wildcard expansion
            if part == '*' or part == '[]':
                if isinstance(cur, (list, tuple)):
                    next_values.extend(list(cur))
                elif isinstance(cur, dict):
                    next_values.extend([cur[k] for k in cur.keys()])
                else:
                    next_values.append(None)
                continue
            # filter ?cond
            if m_filter:
                prop = m_filter.group(1)
                cond = m_filter.group(2)
                # get the array to filter
                arr = None
                if prop == '' or prop is None:
                    arr = cur
                else:
                    if isinstance(cur, dict):
                        arr = cur.get(prop)
                    else:
                        try:
                            arr = cur[prop]
                        except Exception:
                            arr = None
                if isinstance(arr, (list, tuple)):
                    for el in arr:
                        if matches_filter(el, cond):
                            next_values.append(el)
                else:
                    next_values.append(None)
                continue
            # index pattern prop[index]
            if m_index:
                prop = m_index.group(1)
                idx = int(m_index.group(3))
                val = None
                if prop != '':
                    if isinstance(cur, dict):
                        val = cur.get(prop)
                    else:
                        try:
                            val = cur[prop]
                        except Exception:
                            val = None
                else:
                    val = cur
                if isinstance(val, (list, tuple)):
                    if 0 <= idx < len(val):
                        next_values.append(val[idx])
                    else:
                        next_values.append(None)
                else:
                    next_values.append(None)
                continue
            # expand prop[]
            if m_expand:
                prop = m_expand.group(1)
                val = None
                if prop != '':
                    if isinstance(cur, dict):
                        val = cur.get(prop)
                    else:
                        try:
                            val = cur[prop]
                        except Exception:
                            val = None
                else:
                    val = cur
                if isinstance(val, (list, tuple)):
                    next_values.extend(list(val))
                else:
                    next_values.append(None)
                continue
            # normal property access
            if isinstance(cur, dict):
                next_values.append(cur.get(part))
            else:
                try:
                    next_values.append(cur[part])
                except Exception:
                    next_values.append(None)
        if not next_values:
            next_values = [None]
        current_values = next_values
    return current_values[0] if len(current_values) <= 1 else current_values

# parse wrapper-like args (same as before)
def parse_wrapper_args(argv):
    raw = ' '.join(argv)
    m = re.search(r'(?i)(?:/f|/file)\s+(".*?"|\S+)', raw)
    jsonfile = "data.json"
    if m:
        f = m.group(1).strip('"')
        jsonfile = f
        raw = raw.replace(m.group(0), '').strip()
    m2 = re.match(r'(?i)/compare\b\s*(.*)', raw)
    if m2:
        mode = "compare"
        payload = m2.group(1).strip()
    else:
        mode = "read"
        payload = raw.strip()
    return mode, payload, jsonfile

def print_value_label(label, v):
    if isinstance(v, (list, dict)):
        print(f"{label} : {json.dumps(v, ensure_ascii=False)}")
    else:
        print(f"{label} : {v}")

def print_help():
    help_text = """
jsoncmd - ferramenta simples para consultar JSON via linha de comando.

USO GERAL:
  jsoncmd key1,key2,... [/f arquivo.json]
    - Le os caminhos/chaves especificados do JSON e imprime os valores.
    - Exemplo: jsoncmd personagens[].nome /f "meus_personagens.json"
    - Nome padrao de json: data.json

  jsoncmd /compare left,right [/f arquivo.json]
    - Compara left com right. right pode ser:
      * @literal -> usa literal (suporta b64:base64data)
      * outro caminho no JSON
    - Exemplo: jsoncmd /compare personagens[].nome,Goku /f data.json
      Exemplo com literal: jsoncmd /compare personagens[].nome,@Goku

OPCOES IMPORTANTES:
  /?                - Exibe esta ajuda.
  /f arquivo.json   - Especifica arquivo JSON (padrão: data.json).
  /compare          - Modo de comparação (veja acima).
  @literal          - Prefixe com @ para passar literal (use b64:... para base64).
  Suporta filtros no estilo: personagens[?nome=="Goku"]
  Suporta index: personagens[2].nome
  Suporta expansao: personagens[].nome ou *

CODIGOS DE SAIDA:
  0  - OK (encontrado ou exibido)
  1  - Diferença / não encontrado (compare/match fail)
  2  - Uso incorreto / ajuda
  3  - Arquivo JSON não encontrado
  4  - Erro ao parsear JSON
  5  - Erro ao decodificar Base64

EXEMPLOS:
  jsoncmd personagens[?raca=="Saiyajin"].nome /f dados.json
  jsoncmd personagens[].nome
  jsoncmd /compare personagens[].nome,@Goku

"""
    print(help_text.strip())

def main(argv):
    # if any Windows-style help parameter present, show help
    for a in argv:
        if a.strip() in ('/?', '/h', '-h', '--help'):
            print_help()
            sys.exit(EXIT_USAGE)

    if not argv:
        print("Uso: jsoncmd key1,key2,... [/f arquivo.json]  OR  jsoncmd /compare left,right [/f arquivo.json]")
        sys.exit(EXIT_USAGE)

    mode, payload, jsonfile = parse_wrapper_args(argv)

    if not os.path.exists(jsonfile):
        print(f"Arquivo JSON nao encontrado: {jsonfile}", file=sys.stderr)
        sys.exit(EXIT_NOFILE)
    try:
        with open(jsonfile, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print("Erro ao ler/parsear JSON:", e, file=sys.stderr)
        sys.exit(EXIT_PARSE_ERROR)

    if mode == "read":
        keys = [k.strip() for k in payload.split(',') if k.strip()]
        for k in keys:
            val = get_json_value(data, k)
            if isinstance(val, (list, tuple)):
                for idx, item in enumerate(val):
                    label = k.replace('[]', f'[{idx}]').replace('*', f'[{idx}]')
                    print_value_label(label, item)
            else:
                print_value_label(k, val)
        sys.exit(EXIT_OK)
    else:
        parts = [p.strip() for p in payload.split(',', 1)]
        if len(parts) != 2:
            print("Uso incorreto /compare", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        leftPath = parts[0]
        rightToken = parts[1]
        if rightToken.startswith('@'):
            rightValRaw = rightToken[1:]
            rightVal = decode_literal(rightValRaw)
        else:
            rightVal = get_json_value(data, rightToken)
        sRight = rightVal if isinstance(rightVal, str) else canonical_string(rightVal)

        mex = re.match(r'^(.*)\.([^\.\[\]]+)$', leftPath)
        if mex:
            prefix = mex.group(1)
            finalToken = mex.group(2)
            if finalToken.lower() == sRight.lower():
                arr = get_json_value(data, prefix)
                found = False
                if isinstance(arr, (list, tuple)):
                    for el in arr:
                        candidate = el if isinstance(el, str) else canonical_string(el)
                        if candidate.lower() == sRight.lower():
                            found = True
                            break
                else:
                    single = arr if isinstance(arr, str) else canonical_string(arr)
                    if single.lower() == sRight.lower():
                        found = True
                print("EXISTE" if found else "NAO EXISTE")
                sys.exit(EXIT_OK if found else EXIT_DIFF)

        leftVals = get_json_value(data, leftPath)
        matches = []
        if isinstance(leftVals, (list, tuple)):
            for i, lv in enumerate(leftVals):
                sLeft = lv if isinstance(lv, str) else canonical_string(lv)
                if sLeft.lower() == sRight.lower():
                    matches.append((i, lv))
        else:
            sLeft = leftVals if isinstance(leftVals, str) else canonical_string(leftVals)
            if sLeft.lower() == sRight.lower():
                matches.append((0, leftVals))

        if matches:
            print(f"ENCONTRADO(s): {len(matches)}")
            for idx, val in matches:
                if isinstance(val, (list, dict)):
                    print(f"[{idx}] : {json.dumps(val, ensure_ascii=False)}")
                else:
                    print(f"[{idx}] : {val}")
            sys.exit(EXIT_OK)
        else:
            print("NAO foram encontrados itens.")
            sys.exit(EXIT_DIFF)

if __name__ == "__main__":
    main(sys.argv[1:])