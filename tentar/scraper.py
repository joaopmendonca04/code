import json
import requests
from bs4 import BeautifulSoup


def extrair_deputados_automatico():
  url_base = "http://base.alra.pt:82/4DACTION/w_deputados"

  print("A aceder à lista de deputados...")
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
      )
  }

  response = requests.get(url_base, headers=headers)
  response.encoding = "windows-1252"
  soup = BeautifulSoup(response.text, "html.parser")

  deputados_lista = []
  tabela = soup.find("table")

  if tabela:
    linhas = tabela.find_all("tr")
    for linha in linhas:
      colunas = linha.find_all("td")
      if len(colunas) >= 3:
        nome = colunas[0].text.strip()
        partido = colunas[1].text.strip()
        circulo = colunas[2].text.strip()

        if nome and nome.lower() != "deputado":
          # Formatar o nome para criar o nome do ficheiro da foto (ex: "Adolfo Vasconcelos" -> "AdolfoVasconcelos.jpg")
          # Removemos espaços e tratamos acentos comuns
          nome_formatado = (
              nome.replace(" ", "")
              .replace("á", "a")
              .replace("é", "e")
              .replace("í", "i")
              .replace("ó", "o")
              .replace("ú", "u")
              .replace("à", "a")
              .replace("â", "a")
              .replace("ê", "e")
              .replace("ô", "o")
              .replace("ç", "c")
              .replace("ã", "a")
              .replace("õ", "o")
              .replace("Á", "A")
          )

          # Construir o URL oficial direto da foto
          foto_url = f"https://online.alra.pt/deputadosEcra/images/Deputados/{nome_formatado}.jpg"

          deputados_lista.append({
              "nome": nome,
              "partido": partido,
              "circulo": circulo,
              "foto": foto_url,
          })
          print(f"Processado: {nome} -> {foto_url}")
          if len(deputados_lista) >= 57:
            break

  # Guardar no ficheiro JSON
  with open("tentar/deputados.json", "w", encoding="utf-8") as f:
    json.dump(deputados_lista, f, ensure_ascii=False, indent=4)

  print(
      f"Sucesso! Extraídos {len(deputados_lista)} deputados com as respetivas"
      " fotos automáticas."
  )


if __name__ == "__main__":
  extrair_deputados_automatico()
