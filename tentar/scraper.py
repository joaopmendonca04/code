from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import unicodedata
from bs4 import BeautifulSoup
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
BASE_4D = "http://base.alra.pt:82/4DACTION"


def limpar_texto(texto):
  if not texto:
    return ""
  # Corrige aspas tipográficas e travessões do Windows-1252
  texto = (
      texto.replace("\x93", '"')
      .replace("\x94", '"')
      .replace("\x96", "-")
      .replace("\x97", "-")
      .replace("\xa0", " ")
  )
  return re.sub(r"\s+", " ", texto).strip()


def formatar_nome_foto(nome):
  # Remove espaços e quaisquer acentos/tis de forma universal (João -> Joao, Simão -> Simao)
  sem_acentos = "".join(
      c
      for c in unicodedata.normalize("NFD", nome)
      if unicodedata.category(c) != "Mn"
  )
  return sem_acentos.replace(" ", "")


def obter_soup(url):
  resp = requests.get(url, headers=HEADERS, timeout=20)
  html = resp.content.decode("cp1252", errors="replace")
  return BeautifulSoup(html, "html.parser")


def extrair_id_deputado(href):
  # Extrai o número final de links como "w_transpa_dep_historico/1353" ou "?id=1353"
  match = re.search(r"(\d+)(?!.*\d)", href)
  return match.group(1) if match else None


def parse_historico(soup):
  dados = {
      "legislatura": "XIII LEGISLATURA",
      "periodos": [],
      "cargos_desempenha": [],
      "comissoes_anteriores": [],
      "comissoes_atuais": [],
      "intervencoes": [],
      "requerimentos": [],
  }

  linhas = [limpar_texto(l) for l in soup.get_text("\n").split("\n")]
  linhas = [l for l in linhas if l]

  secao = None
  i = 0
  while i < len(linhas):
    linha = linhas[i]
    upper = linha.upper()

    if "LEGISLATURA" in upper:
      dados["legislatura"] = linha
    elif "PERÍODO(S) DO EXERCÍCIO" in upper:
      secao = "periodos"
    elif "CARGOS QUE DESEMPENHA" in upper:
      secao = "cargos_desempenha"
    elif "COMISSÕES A QUE PERTENCEU" in upper:
      secao = "comissoes_anteriores"
    elif "COMISSÕES A QUE PERTENCE" in upper:
      secao = "comissoes_atuais"
    elif "INTERVENÇÕES DIVERSAS" in upper:
      secao = "intervencoes"
    elif upper == "REQUERIMENTOS":
      secao = "requerimentos"
    elif secao in (
        "periodos",
        "cargos_desempenha",
        "comissoes_anteriores",
        "comissoes_atuais",
    ):
      if (
          not linha.startswith("Grupo Parlamentar")
          and not linha.startswith("Circulo")
          and not linha.startswith("Círculo")
      ):
        dados[secao].append(linha.lstrip("- ").strip())
    elif secao in ("intervencoes", "requerimentos"):
      if re.match(r"^\d{2}/\d{2}/\d{4}$", linha) and i + 1 < len(linhas):
        dados[secao].append({"data": linha, "assunto": linhas[i + 1]})
        i += 1
    i += 1

  return dados



def parse_pares_chave_valor(soup, mapa_campos):
  resultado = {v: "" for v in mapa_campos.values()}
  linhas = [limpar_texto(l) for l in soup.get_text("\n").split("\n")]
  linhas = [l for l in linhas if l]
  rotulos_lower = {r.lower() for r in mapa_campos.keys()}

  for idx, linha in enumerate(linhas):
    for rotulo, chave in mapa_campos.items():
      if linha.lower() == rotulo.lower():
        valores = []
        j = idx + 1
        while j < len(linhas) and linhas[j].lower() not in rotulos_lower:
          valores.append(linhas[j])
          j += 1
        resultado[chave] = " ; ".join(valores)
  return resultado



def parse_biografia(soup):
  mapa = {
      "Nome completo": "nome_completo",
      "Data de nascimento": "nascimento",
      "Estado civil": "estado_civil",
      "Habilitações literárias": "habilitacoes",
      "Data de conclusão": "data_conclusao",
      "Profissão": "profissao",
      "Regime de exclusividade": "exclusividade",
      "Cargo(s) que desempenha": "cargos",
      "Contactos": "email",
  }
  return parse_pares_chave_valor(soup, mapa)


def parse_interesses(soup):
  mapa = {
      "Cargo(s) exercido(s)": "cargos_exercidos",
      "Cargos sociais": "cargos_sociais",
      "Apoios ou benefícios": "apoios",
      "Serviços prestados": "servicos",
      "Sociedades": "sociedades",
      "Outras situações": "outras",
  }
  return parse_pares_chave_valor(soup, mapa)


def parse_vencimentos(soup):
  vencimentos = []
  for tr in soup.find_all("tr"):
    cols = [limpar_texto(td.get_text()) for td in tr.find_all(["td", "th"])]
    if len(cols) >= 3 and re.match(r"^\d{4}$", cols[0]):
      valor_bruto = cols[2]
      partes = valor_bruto.split(" - ", 1)
      vencimentos.append({
          "ano": cols[0],
          "mes": cols[1],
          "liquido": partes[0].strip(),
          "obs": partes[1].strip() if len(partes) > 1 else "",
      })
  return vencimentos


def parse_presencas(soup):
  presencas = []
  linhas = [limpar_texto(l) for l in soup.get_text("\n").split("\n")]
  for linha in linhas:
    # Padrão: "23/10/2026 - Presente" ou "23/10/2026 - Falta Justificada"
    match = re.match(r"^(\d{2}/\d{2}/\d{4})\s*-\s*(.+)$", linha)
    if match:
      presencas.append(
          {"data": match.group(1), "estado": match.group(2).strip()}
      )
  return presencas


def processar_deputado(dep_base):
  dep_id = dep_base["id"]
  nome = dep_base["nome"]
  foto_url = f"https://online.alra.pt/deputadosEcra/images/Deputados/{formatar_nome_foto(nome)}.jpg"

  registro = {
      "id": dep_id,
      "nome": nome,
      "partido": dep_base["partido"],
      "circulo": dep_base["circulo"],
      "foto": foto_url,
      "historico": {},
      "biografia": {},
      "interesses": {},
      "vencimentos": [],
      "presencas": [],
  }

  if not dep_id:
    return registro

  endpoints = {
      "historico": (
          f"{BASE_4D}/w_transpa_dep_historico/{dep_id}",
          parse_historico,
      ),
      "biografia": (f"{BASE_4D}/w_transpa_dep_bio/{dep_id}", parse_biografia),
      "interesses": (
          f"{BASE_4D}/w_transpa_dep_inter/{dep_id}",
          parse_interesses,
      ),
      "vencimentos": (
          f"{BASE_4D}/w_transpa_dep_venc/{dep_id}",
          parse_vencimentos,
      ),
      "presencas": (
          f"{BASE_4D}/w_transpa_dep_presenca/{dep_id}",
          parse_presencas,
      ),
  }

  for chave, (url, parser_fn) in endpoints.items():
    try:
      soup = obter_soup(url)
      registro[chave] = parser_fn(soup)
    except Exception as e:
      print(f"[Aviso] Falha em {chave} para {nome} (ID {dep_id}): {e}")

  return registro


def main():
  print("1. A obter a lista dos 57 deputados em funções...")
  soup_lista = obter_soup(f"{BASE_4D}/w_deputados")
  tabela = soup_lista.find("table")

  base_deputados = []
  if tabela:
    for linha in tabela.find_all("tr"):
      colunas = linha.find_all("td")
      if len(colunas) >= 3:
        nome = limpar_texto(colunas[0].get_text())
        partido = limpar_texto(colunas[1].get_text())
        circulo = limpar_texto(colunas[2].get_text())
        link = colunas[0].find("a")
        dep_id = (
            extrair_id_deputado(link["href"])
            if link and link.get("href")
            else None
        )

        if nome and nome.lower() != "deputado":
          base_deputados.append({
              "id": dep_id,
              "nome": nome,
              "partido": partido,
              "circulo": circulo,
          })
          if len(base_deputados) >= 57:
            break

  print(
      f"2. Encontrados {len(base_deputados)} deputados. A recolher as 5 abas em"
      " paralelo..."
  )

  resultados_ordenados = [None] * len(base_deputados)
  with ThreadPoolExecutor(max_workers=8) as executor:
    futuros = {
        executor.submit(processar_deputado, dep): idx
        for idx, dep in enumerate(base_deputados)
    }
    concluidos = 0
    for futuro in as_completed(futuros):
      idx = futuros[futuro]
      resultados_ordenados[idx] = futuro.result()
      concluidos += 1
      print(
          f"   [{concluidos}/{len(base_deputados)}]"
          f" {resultados_ordenados[idx]['nome']}"
      )

  with open("tentar/deputados.json", "w", encoding="utf-8") as f:
    json.dump(resultados_ordenados, f, ensure_ascii=False, indent=4)

  print(
      "\nConcluído! Todos os dados detalhados foram guardados em"
      " 'deputados.json'."
  )


if __name__ == "__main__":
  main()
