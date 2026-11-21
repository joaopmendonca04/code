#!/usr/bin/env python3
"""
Análise de Legibilidade Textual para português.

Implementa as fórmulas adaptadas descritas em https://legibilidade.com/sobre :
  - Flesch Reading Ease (F)            escala 0-100
  - Índice Gulpease                    escala 0-100
  - Flesch-Kincaid Grade Level (FK)    anos de escolaridade
  - Gunning Fog adaptado (GF)          anos de escolaridade
  - Automated Readability Index (ARI)  anos de escolaridade
  - Coleman-Liau (CL)                  anos de escolaridade
  - Fórmula final = média de FK, GF, ARI e CL

Aceita .txt e .pdf. Antes de calcular, limpa o "ruído" que não é texto corrido:
  PDF:  cabeçalhos/rodapés (por posição e por repetição entre páginas),
        números de página, texto dentro de imagens, páginas digitalizadas (aviso)
  Todos: numeração/marcadores (1., 2), a), •), referências legislativas
        (Decreto-Lei n.º 12/2020, artigo 5.º, ...), URLs, emails

Instalação (só para PDFs):   pip3 install pymupdf

Exemplos:
  python3 legibilidade.py texto.txt
  python3 legibilidade.py relatorio.pdf --guardar-limpo limpo.txt
  python3 legibilidade.py relatorio.pdf --paginas 3-12 --ignorar "Grupo Parlamentar"
  python3 legibilidade.py relatorio.pdf --lista palavras_frequentes.txt --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, asdict, field

# ----------------------------------------------------------------------------
# Constantes de tokenização
# ----------------------------------------------------------------------------

LETRAS = "A-Za-zÀ-ÖØ-öø-ÿ"
RE_PALAVRA = re.compile(rf"[{LETRAS}]+(?:-[{LETRAS}]+)*")
RE_FIM_FRASE = re.compile(r"([.!?…]+[\"'”»)\]]*)(\s+|$)")

ABREVIATURAS = {
    "sr", "sra", "srs", "sras", "dr", "dra", "drs", "dras", "prof", "profa",
    "eng", "engª", "exmo", "exma", "etc", "ex", "pág", "págs", "cap", "fig",
    "art", "av", "tel", "min", "máx", "vol", "n", "nº", "p", "pp", "cf", "vs",
}

# ----------------------------------------------------------------------------
# LIMPEZA DE TEXTO
# ----------------------------------------------------------------------------


@dataclass
class RelatorioLimpeza:
    paginas: int = 0
    paginas_sem_texto: list = field(default_factory=list)
    linhas_margem: int = 0
    linhas_repetidas: int = 0
    exemplos_repetidas: list = field(default_factory=list)
    linhas_numero_pagina: int = 0
    blocos_em_imagens: int = 0
    marcadores_removidos: int = 0
    referencias_legais: int = 0
    urls_emails_citacoes: int = 0
    linhas_ignoradas: int = 0

    def imprimir(self, file=sys.stderr) -> None:
        p = lambda s: print(s, file=file)
        p("--- Limpeza aplicada ---")
        if self.paginas:
            p(f" Páginas lidas:                     {self.paginas}")
            p(f" Linhas em cabeçalho/rodapé (margem): {self.linhas_margem}")
            p(f" Linhas repetidas entre páginas:     {self.linhas_repetidas}")
            for ex in self.exemplos_repetidas[:5]:
                p(f"     ex.: {ex!r}")
            p(f" Números de página:                  {self.linhas_numero_pagina}")
            p(f" Blocos de texto sobre imagens:      {self.blocos_em_imagens}")
            if self.paginas_sem_texto:
                p(f" ATENÇÃO páginas sem texto (digitalizadas? precisam de OCR): "
                  f"{self.paginas_sem_texto}")
        p(f" Marcadores/numeração removidos:     {self.marcadores_removidos}")
        p(f" Referências legislativas removidas: {self.referencias_legais}")
        p(f" URLs/emails/citações removidos:     {self.urls_emails_citacoes}")
        if self.linhas_ignoradas:
            p(f" Linhas ignoradas (--ignorar):       {self.linhas_ignoradas}")
        p("")


# --- numeração / marcadores no início da linha ---
RE_MARCADOR = re.compile(
    r"^\s*(?:"
    r"\(\d{1,3}\)"                         # (1)
    r"|\d{1,3}(?:\.\d{1,3})+\.?\s"         # 1.2   1.2.3
    r"|\d{1,3}[.)\-–—:]"                   # 1.   1)   1-   1:
    r"|\d{1,3}\.?[ºª°]"                    # 1.º  1º
    r"|\(?[a-zA-Z]\)"                      # a)   (a)
    r"|\(?[ivxIVX]{1,5}\)"                 # i)   (iv)
    r"|[IVX]{1,5}\."                       # IV.
    r"|[•▪■●○·*]"                          # bullets
    r"|[\-–—](?=\s)"                       # travessão/hífen de lista
    r")\s*"
)

# --- referências legislativas ---
_PREFIXO = (r"(?:(?:ao\s+abrigo|nos\s+termos|de\s+acordo\s+com|conforme|segundo)\s+)?"
            r"(?:d[oa]s?\s+|n[oa]s?\s+|pel[oa]s?\s+|ao\s+|à\s+)?")
_NUM_DIPLOMA = r"(?:n\.?\s*[ºª°]\s*)?\d+(?:-[A-Za-z])?/\d{2,4}(?:/[A-Z]+)?"
_DATA = r"(?:,?\s+de\s+\d{1,2}\s+de\s+[a-zçãé]+(?:\s+de\s+\d{4})?)?"
RE_DIPLOMA = re.compile(
    _PREFIXO + r"\b(?:Decreto[- ]Lei|Decreto Legislativo Regional|Decreto Legislativo|"
    r"Decreto Regulamentar Regional|Decreto Regulamentar|Decreto|"
    r"Lei Org[âa]nica|Lei Constitucional|Lei|Portaria|Despacho|"
    r"Resolu[çc][ãa]o(?: da Assembleia da Rep[úu]blica| do Conselho de Ministros"
    r"| do Governo Regional)?|Regulamento(?: \((?:UE|CE)\))?|Diretiva|Directiva|Aviso)"
    r"\s+" + _NUM_DIPLOMA + _DATA,
    re.IGNORECASE,
)
RE_DR = re.compile(
    _PREFIXO + r"Di[áa]rio da Rep[úu]blica(?:\s*,?\s*\d\.[ªa]\s*s[ée]rie)?"
    r"(?:\s*,?\s*n\.?\s*[ºª°]\s*\d+(?:/\d{2,4})?)?",
    re.IGNORECASE,
)
RE_ARTIGO = re.compile(
    _PREFIXO + r"(?:al[íi]neas?\s+[a-z]\)\s+d[oa]s?\s+)?"
    r"(?:n\.?\s*[ºª°]s?\s*\d+\s+d[oa]s?\s+)?"
    r"\bartigos?\s+\d+\.?[ºª°]?(?:-[A-Z])?"
    r"(?:\s*(?:,|e)\s*\d+\.?[ºª°]?(?:-[A-Z])?)*"
    r"(?:\s+d[oa]\s+(?:C[óo]digo\s+\w+(?:\s+\w+)?"
    r"|Constitui[çc][ãa]o(?:\s+da\s+Rep[úu]blica(?:\s+Portuguesa)?)?))?",
    re.IGNORECASE,
)

RE_URL_EMAIL = re.compile(r"(?:https?://|www\.)[^\s)\]]*[^\s.,;:!?)\]]|\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
RE_CITACAO = re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]")

RE_NUM_PAGINA = re.compile(
    r"^\s*[-–—]?\s*(?:p[áa]g(?:ina|\.)?\s*)?\d{1,4}\s*(?:(?:de|/)\s*\d{1,4})?\s*[-–—]?\s*$",
    re.IGNORECASE,
)


RE_PENDENTE = re.compile(
    r"\b(?:alterad[oa]s?|republicad[oa]s?|retificad[oa]s?|pel[oa]s?|d[oa]s?|n[oa]s?"
    r"|ao|à|de|em|e|ou|os?|as?)\s*(?=[,;:.!?]|$)", re.IGNORECASE)


def _arrumar(l: str) -> str:
    l = re.sub(r"\(\s*\)|\[\s*\]", " ", l)
    l = re.sub(r"\b(?:e|ou)\s*(?=[,.;:!?])", " ", l)
    l = re.sub(r"[,;:]+\s*([.!?…])", r"\1", l)
    l = re.sub(r"\s+([,.;:!?)\]])", r"\1", l)
    l = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", l)
    l = re.sub(r"\s+", " ", l)
    l = re.sub(r"^[\s,;:.\-–—]+", "", l)
    return l.strip()


def limpar_texto(texto: str, rel: RelatorioLimpeza, numeracao: bool = True,
                 legislacao: bool = True, ignorar: list | None = None) -> str:
    """Limpeza ao nível da linha/parágrafo, comum a .txt e .pdf."""
    ignorar_re = [re.compile(r, re.IGNORECASE) for r in (ignorar or [])]
    saida = []
    for linha in texto.split("\n"):
        l = linha.strip()
        if not l:
            continue
        if any(r.search(l) for r in ignorar_re):
            rel.linhas_ignoradas += 1
            continue

        l, n1 = RE_URL_EMAIL.subn(" ", l)
        l, n2 = RE_CITACAO.subn(" ", l)
        rel.urls_emails_citacoes += n1 + n2

        if numeracao:
            m = RE_MARCADOR.match(l)
            if m:
                l = l[m.end():]
                rel.marcadores_removidos += 1

        if legislacao:
            removeu = 0
            for rx in (RE_ARTIGO, RE_DIPLOMA, RE_DR):
                l, n = rx.subn(" ", l)
                removeu += n
            rel.referencias_legais += removeu
            if removeu:  # apanha "alterado,", "pela", "e" que ficaram pendurados
                for _ in range(2):
                    l = RE_PENDENTE.sub(" ", l)

        l = _arrumar(l)
        if not re.search(rf"[{LETRAS}]", l):
            continue
        saida.append(l)
    return "\n".join(saida)


# ----------------------------------------------------------------------------
# LEITURA DE PDF
# ----------------------------------------------------------------------------


def _norm_linha(l: str) -> str:
    """Normaliza para comparar linhas entre páginas. Só em linhas curtas (≤6
    palavras, típicas de cabeçalhos/rodapés) é que os números são ignorados,
    para 'Relatório 2024 - pág. 3' e '... pág. 4' contarem como a mesma linha."""
    n = re.sub(r"\s+", " ", l.strip().lower())
    return re.sub(r"\d+", "#", n) if len(n.split()) <= 6 else n


def _inter_area(a, b) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return w * h if w > 0 and h > 0 else 0.0


def _juntar_linhas(linhas: list) -> list:
    """Junta linhas de um bloco em parágrafos (desfaz hifenização; cada marcador
    de lista começa um parágrafo novo)."""
    paragrafos = []
    for l in linhas:
        if not paragrafos or RE_MARCADOR.match(l):
            paragrafos.append(l)
        elif paragrafos[-1].endswith("-") and l[:1].islower():
            paragrafos[-1] = paragrafos[-1][:-1] + l
        else:
            paragrafos[-1] += " " + l
    return paragrafos


def parse_paginas(s: str | None) -> set | None:
    if not s:
        return None
    out = set()
    for parte in s.split(","):
        parte = parte.strip()
        if "-" in parte:
            a, b = parte.split("-")
            out.update(range(int(a), int(b) + 1))
        elif parte:
            out.add(int(parte))
    return out


def extrair_pdf(caminho: str, rel: RelatorioLimpeza, margem_topo: float = 0.07,
                margem_fundo: float = 0.07, paginas: set | None = None,
                cortar: str | None = None) -> str:
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz  # type: ignore
        except ImportError:
            sys.exit("Para ler PDFs é preciso instalar:  pip install pymupdf")

    doc = fitz.open(caminho)
    rel.paginas = len(doc)
    por_pagina = []  # por página: lista de (linhas, em_zona, cheio)
    cortar_rx = re.compile(cortar, re.IGNORECASE) if cortar else None
    parar = False

    for idx in range(len(doc)):
        if paginas and (idx + 1) not in paginas:
            continue
        page = doc[idx]
        W, H = page.rect.width, page.rect.height
        area_pag = W * H

        # imagens "normais" (ignora fundos que ocupam quase a página toda)
        imgs = []
        try:
            for info in page.get_image_info():
                r = fitz.Rect(info["bbox"])
                if r.width * r.height < 0.6 * area_pag:
                    imgs.append(r)
        except Exception:
            pass

        brutos, total_chars = [], 0
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            linhas = []  # (texto, x_direito)
            for ln in b.get("lines", []):
                t = "".join(sp["text"] for sp in ln["spans"]).strip()
                if t:
                    linhas.append((t, ln["bbox"][2]))
            if not linhas:
                continue
            x0, y0, x1, y1 = b["bbox"]
            if cortar_rx and any(cortar_rx.search(t) for t, _ in linhas):
                parar = True  # ignora este bloco e tudo o que vem a seguir
                break
            total_chars += sum(len(t) for t, _ in linhas)

            # 1) cabeçalho / rodapé por posição
            if y1 <= H * margem_topo or y0 >= H * (1 - margem_fundo):
                rel.linhas_margem += len(linhas)
                continue
            # 2) texto sobreposto a imagens (legendas, assinaturas, gráficos)
            area_bloco = max((x1 - x0) * (y1 - y0), 1e-6)
            br = fitz.Rect(x0, y0, x1, y1)
            if any(_inter_area(br, im) / area_bloco > 0.5 for im in imgs):
                rel.blocos_em_imagens += 1
                continue
            em_zona = y1 <= H * 0.15 or y0 >= H * 0.88  # topo/fundo da página
            brutos.append((linhas, em_zona))

        if total_chars < 20:
            rel.paginas_sem_texto.append(idx + 1)

        # borda direita do texto corrido: linhas que lá chegam continuam na seguinte
        xs = [x for linhas, z in brutos if not z for _, x in linhas]
        dir_ = max(xs) if xs else W
        blocos = [([t for t, _ in linhas], z, linhas[-1][1] >= dir_ - 0.02 * W)
                  for linhas, z in brutos]
        por_pagina.append(blocos)
        if parar:
            break

    # 3) cabeçalhos/rodapés por repetição entre páginas
    repetidas = set()
    n_pag = len(por_pagina)
    if n_pag >= 3:
        cont = Counter()
        for blocos in por_pagina:
            vistas = {_norm_linha(l) for bl, z, _ in blocos if z
                      for l in bl if len(l.split()) <= 15}
            cont.update(vistas)
        limiar = max(3, int(0.4 * n_pag))
        repetidas = {k for k, v in cont.items() if v >= limiar and len(k) >= 4}

    paragrafos = []  # (texto, termina_na_margem_direita)
    for blocos in por_pagina:
        for bl, zona, cheio in blocos:
            linhas = []
            for l in bl:
                if RE_NUM_PAGINA.match(l):
                    rel.linhas_numero_pagina += 1
                    continue
                if zona and len(l.split()) <= 15 and _norm_linha(l) in repetidas:
                    rel.linhas_repetidas += 1
                    if l not in rel.exemplos_repetidas:
                        rel.exemplos_repetidas.append(l)
                    continue
                linhas.append(l)
            if linhas:
                ps = _juntar_linhas(linhas)
                for i, p in enumerate(ps):
                    paragrafos.append((p, cheio and i == len(ps) - 1))

    # 4) parágrafos que continuam no bloco/página seguinte
    #    (a linha anterior chegou à margem direita sem pontuação final, ou o
    #     seguinte começa em minúscula)
    unidos: list = []
    for p, cheio in paragrafos:
        if unidos:
            ant, _ = unidos[-1]
            if (not re.search(r"[.!?…:;»]\s*$", ant) and not RE_MARCADOR.match(p)
                    and (p[:1].islower() or unidos[-1][1])):
                if ant.endswith("-") and p[:1].islower():
                    unidos[-1] = [ant[:-1] + p, cheio]
                else:
                    unidos[-1] = [ant + " " + p, cheio]
                continue
        unidos.append([p, cheio])
    return "\n".join(t for t, _ in unidos)


def finalizar_pdf(texto: str, min_titulo: int = 4, pontuar: bool = True) -> str:
    """Depois da limpeza: descarta títulos curtos sem pontuação (Objeto,
    Entrada em vigor, Notas:) e acrescenta ponto final aos restantes parágrafos
    sem pontuação, para não se colarem à frase seguinte."""
    out = []
    for p in texto.split("\n"):
        p = p.strip()
        if not p:
            continue
        terminal = re.search(r"[.!?…]\s*$", p)
        if not terminal and min_titulo and len(p.split()) < min_titulo:
            continue
        if pontuar and not terminal:
            p = re.sub(r"[,;:\s]+$", "", p) + "."
        out.append(p)
    return "\n".join(out)


def cortar_a_partir(texto: str, regex: str) -> str:
    """Descarta tudo a partir da primeira linha que contenha a expressão."""
    rx = re.compile(regex, re.IGNORECASE)
    out = []
    for l in texto.split("\n"):
        if rx.search(l):
            break
        out.append(l)
    return "\n".join(out)


# ----------------------------------------------------------------------------
# Frases / palavras / sílabas
# ----------------------------------------------------------------------------


def dividir_frases(texto: str) -> list[str]:
    texto = re.sub(r"\s+", " ", texto.strip())
    if not texto:
        return []

    frases, inicio = [], 0
    for m in RE_FIM_FRASE.finditer(texto):
        fim = m.end(1)
        if m.group(1) == ".":
            anterior = re.search(rf"([{LETRAS}]+)$", texto[inicio:fim - 1])
            if anterior and anterior.group(1).lower() in ABREVIATURAS:
                continue
            if anterior and len(anterior.group(1)) == 1 and anterior.group(1).isupper():
                continue
        frase = texto[inicio:fim].strip()
        if frase:
            frases.append(frase)
        inicio = m.end()
    resto = texto[inicio:].strip()
    if resto:
        frases.append(resto)
    return frases


VOGAIS_FORTES = set("aáâãàeéêoóôõ")
VOGAIS_FRACAS = set("iu")
VOGAIS_FRACAS_ACENTUADAS = set("íúï")
TODAS_VOGAIS = VOGAIS_FORTES | VOGAIS_FRACAS | VOGAIS_FRACAS_ACENTUADAS | set("ü")
DITONGOS_NASAIS = {("ã", "o"), ("ã", "e"), ("õ", "e")}


def contar_silabas(palavra: str) -> int:
    p = palavra.lower().replace("-", "")
    p = re.sub(r"([qg])u([eéêiíî])", r"\1\2", p)

    silabas = 0
    i, n = 0, len(p)
    while i < n:
        if p[i] in TODAS_VOGAIS:
            silabas += 1
            while i + 1 < n and p[i + 1] in TODAS_VOGAIS:
                a, b = p[i], p[i + 1]
                if (a, b) in DITONGOS_NASAIS:
                    pass
                elif a in VOGAIS_FORTES and b in VOGAIS_FORTES:
                    silabas += 1
                elif b in VOGAIS_FRACAS_ACENTUADAS or a in VOGAIS_FRACAS_ACENTUADAS:
                    silabas += 1
                i += 1
        i += 1
    return max(silabas, 1)


# ----------------------------------------------------------------------------
# Lista de palavras frequentes / palavras complexas
# ----------------------------------------------------------------------------


def _normalizar(p: str) -> str:
    return unicodedata.normalize("NFC", p.lower())


def carregar_lista(caminho: str, n: int = 5000) -> set[str]:
    palavras = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            palavras.append(_normalizar(linha.split()[0]))
            if len(palavras) >= n:
                break
    return set(palavras)


def e_nome_proprio_ou_sigla(palavra: str, inicio_de_frase: bool) -> bool:
    if len(palavra) > 1 and palavra.isupper():
        return True
    if palavra[0].isupper() and not inicio_de_frase:
        return True
    return False


# ----------------------------------------------------------------------------
# Cálculo
# ----------------------------------------------------------------------------


@dataclass
class Resultado:
    letras: int
    silabas: int
    palavras: int
    frases: int
    palavras_complexas: int
    criterio_complexas: str
    flesch: float
    gulpease: float
    flesch_kincaid: float
    gunning_fog: float
    ari: float
    coleman_liau: float
    formula_final: float


def analisar(texto: str, lista_frequentes: set[str] | None = None) -> Resultado:
    frases = dividir_frases(texto)
    n_frases = len(frases)

    n_palavras = n_letras = n_silabas = n_complexas = 0
    for frase in frases:
        for idx, m in enumerate(RE_PALAVRA.finditer(frase)):
            palavra = m.group(0)
            n_palavras += 1
            n_letras += len(palavra.replace("-", ""))
            sil = contar_silabas(palavra)
            n_silabas += sil

            if e_nome_proprio_ou_sigla(palavra, inicio_de_frase=(idx == 0)):
                continue
            if lista_frequentes is not None:
                if _normalizar(palavra) not in lista_frequentes:
                    n_complexas += 1
            elif sil >= 4:
                n_complexas += 1

    if n_palavras == 0 or n_frases == 0:
        raise ValueError("O texto não contém palavras/frases analisáveis.")

    P, S, L, Sil, C = n_palavras, n_frases, n_letras, n_silabas, n_complexas

    pal_por_frase = P / S
    sil_por_pal = Sil / P
    letras_por_pal = L / P
    complexas_por_pal = C / P
    frases_por_pal = S / P

    flesch = 226 - 1.04 * pal_por_frase - 72 * sil_por_pal
    gulpease = 89 + (300 * S - 10 * L) / P
    fk = 0.36 * pal_por_frase + 10.4 * sil_por_pal - 18
    gf = 0.49 * pal_por_frase + 19 * complexas_por_pal
    ari = 4.6 * letras_por_pal + 0.44 * pal_por_frase - 20
    cl = 5.4 * letras_por_pal - 21 * frases_por_pal - 14
    final = (fk + gf + ari + cl) / 4

    return Resultado(
        letras=L, silabas=Sil, palavras=P, frases=S, palavras_complexas=C,
        criterio_complexas=(
            "fora das 5000 palavras mais frequentes" if lista_frequentes is not None
            else "4 ou mais sílabas (critério de recurso)"
        ),
        flesch=round(flesch, 1), gulpease=round(gulpease, 1),
        flesch_kincaid=round(fk, 1), gunning_fog=round(gf, 1),
        ari=round(ari, 1), coleman_liau=round(cl, 1),
        formula_final=round(final, 1),
    )


def interpretar_flesch(f: float) -> str:
    if f >= 90: return "muito fácil"
    if f >= 80: return "fácil"
    if f >= 70: return "razoavelmente fácil"
    if f >= 60: return "padrão"
    if f >= 50: return "razoavelmente difícil"
    if f >= 30: return "difícil"
    return "muito difícil"


def interpretar_nivel(n: float) -> str:
    if n <= 6: return "ensino básico (1.º/2.º ciclo) — muito simples"
    if n <= 9: return "ensino básico (3.º ciclo)"
    if n <= 12: return "ensino secundário"
    if n <= 16: return "ensino superior (licenciatura)"
    return "pós-graduação — leitura difícil"


def imprimir(r: Resultado) -> None:
    print("=" * 52)
    print(" ANÁLISE DE LEGIBILIDADE TEXTUAL")
    print("=" * 52)
    print(f" Letras:              {r.letras}")
    print(f" Sílabas (aprox.):    {r.silabas}")
    print(f" Palavras:            {r.palavras}")
    print(f" Frases:              {r.frases}")
    print(f" Palavras complexas:  {r.palavras_complexas}")
    print(f"   critério: {r.criterio_complexas}")
    print("-" * 52)
    print(" Escala 0-100 (maior = mais fácil)")
    print(f"   Flesch Reading Ease: {r.flesch:>6}  ({interpretar_flesch(r.flesch)})")
    print(f"   Gulpease:            {r.gulpease:>6}")
    print("-" * 52)
    print(" Anos de escolaridade (maior = mais difícil)")
    print(f"   Flesch-Kincaid:      {r.flesch_kincaid:>6}")
    print(f"   Gunning Fog:         {r.gunning_fog:>6}")
    print(f"   ARI:                 {r.ari:>6}")
    print(f"   Coleman-Liau:        {r.coleman_liau:>6}")
    print("-" * 52)
    print(f" FÓRMULA FINAL:         {r.formula_final:>6}")
    print(f"   -> {interpretar_nivel(r.formula_final)}")
    print("=" * 52)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Análise de legibilidade para português (.txt e .pdf).")
    ap.add_argument("ficheiro", help=".txt ou .pdf a analisar, ou '-' para stdin")
    ap.add_argument("--lista", help="lista de palavras frequentes (uma por linha, por frequência)")
    ap.add_argument("--json", action="store_true", help="saída em JSON")
    ap.add_argument("--guardar-limpo", metavar="FICHEIRO",
                    help="guarda o texto limpo que foi realmente analisado (para verificares)")
    ap.add_argument("--paginas", help="só estas páginas do PDF, ex.: 3-12 ou 1,4,6-8")
    ap.add_argument("--margem-topo", type=float, default=0.07,
                    help="fração da altura da página tratada como cabeçalho (omissão 0.07)")
    ap.add_argument("--margem-fundo", type=float, default=0.07,
                    help="fração da altura da página tratada como rodapé (omissão 0.07)")
    ap.add_argument("--ignorar", action="append", default=[], metavar="REGEX",
                    help="ignora linhas que contenham esta expressão (pode repetir)")
    ap.add_argument("--manter-numeracao", action="store_true", help="não remove 1., a), •, ...")
    ap.add_argument("--manter-legislacao", action="store_true",
                    help="não remove Decreto-Lei n.º.., artigo 5.º, ...")
    ap.add_argument("--nao-pontuar", action="store_true",
                    help="PDF: não acrescenta ponto final a parágrafos sem pontuação")
    ap.add_argument("--descartar-titulos", type=int, default=4, metavar="N",
                    help="PDF: descarta parágrafos sem pontuação com menos de N palavras "
                         "(títulos como 'Objeto'); 0 desliga (omissão 4)")
    ap.add_argument("--cortar-a-partir", metavar="REGEX",
                    help="descarta tudo a partir da primeira linha que contenha esta "
                         "expressão (ex.: anexos no fim do documento)")
    ap.add_argument("--sem-limpeza", action="store_true", help="analisa o texto tal como está")
    args = ap.parse_args()

    rel = RelatorioLimpeza()

    if args.ficheiro.lower().endswith(".pdf"):
        texto = extrair_pdf(args.ficheiro, rel, args.margem_topo, args.margem_fundo,
                            parse_paginas(args.paginas), args.cortar_a_partir)
    elif args.ficheiro == "-":
        texto = sys.stdin.read()
    else:
        with open(args.ficheiro, encoding="utf-8") as f:
            texto = f.read()

    if args.cortar_a_partir:
        texto = cortar_a_partir(texto, args.cortar_a_partir)

    if not args.sem_limpeza:
        texto = limpar_texto(texto, rel, numeracao=not args.manter_numeracao,
                             legislacao=not args.manter_legislacao, ignorar=args.ignorar)
        rel.imprimir()

    if args.ficheiro.lower().endswith(".pdf"):
        texto = finalizar_pdf(texto, args.descartar_titulos, not args.nao_pontuar)

    if args.guardar_limpo:
        with open(args.guardar_limpo, "w", encoding="utf-8") as f:
            f.write(texto + "\n")
        print(f"Texto limpo guardado em {args.guardar_limpo}\n", file=sys.stderr)

    lista = carregar_lista(args.lista) if args.lista else None
    if lista is None:
        print("Aviso: sem --lista; palavras complexas = 4+ sílabas "
              "(o Gunning Fog fica menos fiel ao ALT).\n", file=sys.stderr)

    try:
        r = analisar(texto, lista)
    except ValueError as e:
        sys.exit(f"Erro: {e}")

    if args.json:
        print(json.dumps({"resultado": asdict(r), "limpeza": asdict(rel)},
                         ensure_ascii=False, indent=2))
    else:
        imprimir(r)


if __name__ == "__main__":
    main()