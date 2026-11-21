import textstat

textstat.set_lang('pt')

def calcular_legibilidade_pt(texto):
    # 1. Contar os elementos do texto
    palavras = textstat.lexicon_count(texto)
    frases = textstat.sentence_count(texto)
    silabas = textstat.syllable_count(texto)

    # Proteção contra textos vazios para não dividir por zero
    if frases == 0 or palavras == 0:
        return 0

    # 2. Calcular as médias
    media_palavras_por_frase = palavras / frases
    media_silabas_por_palavra = silabas / palavras

    # 3. Aplicar a fórmula adaptada para Português (Martins)
    score = 248.835 - (1.015 * media_palavras_por_frase) - (84.6 * media_silabas_por_palavra)
    
    # Devolver o resultado arredondado a 2 casas decimais
    return round(score, 2)

# Os nossos textos de teste
texto_politico = """
Considerando que, a reabilitação da Escola Básica e Secundária das Flores se
encontra há vários anos identificada como uma intervenção necessária,
constando inclusivamente dos Planos Regionais Anuais de 2025 e 2026;
Considerando que, em Julho de 2025, foi lançado um concurso público para a
empreitada de reparação da Escola Básica e Secundária das Flores, com um
preço base de 520 mil euros;
Considerando que, o referido valor da empreitada destinava-se, entre outras
intervenções, à reabilitação das coberturas, das redes de abastecimento de água
e de infra-estruturas eléctricas, bem como à reparação de vãos, pavimentos e
pinturas;
Considerando que, não tendo aquela empreitada avançado, foi lançado um novo
procedimento, com a referência , desta vez com um preço
base de 620 mil euros, representando um aumento de 100 mil euros face ao
procedimento anterior;
Considerando que, o prazo para apresentação de propostas ao referido concurso
terminou no passado dia 19 de Setembro de 2026;
Considerando que, é necessário concretizar-se finalmente uma intervenção que
se reveste de particular importância para a comunidade educativa da ilha das Flores, designadamente perante os problemas recorrentes de infiltrações de
água no edifício escolar;
Vem o Grupo Parlamentar do CHEGA, ao abrigo das disposições estatutárias e
regimentais aplicáveis, requerer que nos sejam prestados os seguintes
esclarecimentos:
"""

texto_simples = "vai te foder, eu sempre te amei, sempre fiz tudo por ti, e tu? quando é que estiveste ao meu lado? Seguraste a minha mão? nada, porque nunca me amaste, nunca me desejaste, fui apenas um momento."

# Executar a nossa própria função
print("--- TESTE DE ACESSIBILIDADE CÍVICA (ADAPTADO PARA PT) ---")
print(f"Texto Burocrático: {calcular_legibilidade_pt(texto_politico)} / 100")
print(f"Texto Simples: {calcular_legibilidade_pt(texto_simples)} / 100")