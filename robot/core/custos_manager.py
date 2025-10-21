# robot/core/custos_manager.py
import logging
import re
from playwright.sync_api import Page, expect, TimeoutError as PlaywrightTimeoutError
from config import COMPROVANTES_DIR

def _limpar_nome_arquivo(texto: str) -> str:
    """Remove caracteres inválidos de uma string para usar como nome de arquivo."""
    # Remove "R$" e espaços extras
    texto = texto.replace('R$', '').strip()
    # Substitui caracteres inválidos por underscore
    texto_limpo = re.sub(r'[\\/*?:"<>|]', '_', texto)
    return texto_limpo

def pesquisar_e_extrair_custas(page: Page, npj: str) -> list[dict]:
    """
    Versão V10:
    1. Usa um seletor específico para a aba visível, resolvendo o 'strict mode violation'.
    2. Mantém a lógica de scroll e espera para garantir a estabilidade.
    3. Mantém a nomenclatura de PDFs e pastas.
    """
    logging.info(f"Iniciando busca detalhada para o NPJ: {npj}")
    resultados_finais = []
    COMPROVANTES_DIR.mkdir(exist_ok=True)

    try:
        # --- ETAPA 1: Pesquisa inicial ---
        input_npj = page.locator("#npj")
        expect(input_npj).to_be_visible(timeout=20000)
        input_npj.fill(npj)
        input_npj.press("Tab")
        logging.info(f"NPJ '{npj}' inserido. Aguardando resultados...")

        # CORREÇÃO: Seletor específico para o container de scroll DENTRO da aba visível.
        seletor_container = "div.tabs__pane.is-visible div[style*='overflow-y: auto']"
        container_scroll = page.locator(seletor_container)
        
        # Espera que o container ÚNICO esteja visível.
        expect(container_scroll).to_be_visible(timeout=20000)
        
        # Aguarda a tabela ter pelo menos uma linha para garantir que carregou
        container_scroll.locator("tr[ng-repeat='item in $data']").first.wait_for(timeout=15000)
        page.wait_for_timeout(1500) # Pausa extra para a UI estabilizar

        # Pega a contagem de linhas
        total_linhas = container_scroll.locator("tr[ng-repeat='item in $data']").count()
        logging.info(f"Encontradas {total_linhas} custa(s) na tabela.")

        # --- ETAPA 2: Loop de extração, uma custa por vez ---
        for i in range(total_linhas):
            logging.info("-" * 40)
            logging.info(f"Analisando custa {i + 1} de {total_linhas}...")

            # Re-localiza a linha dentro do container correto a cada iteração
            linha_atual = container_scroll.locator("tr[ng-repeat='item in $data']").nth(i)
            
            try:
                linha_atual.scroll_into_view_if_needed(timeout=10000)
            except PlaywrightTimeoutError:
                logging.error(f"Não foi possível rolar para a linha {i+1}. Pulando.")
                continue
            
            page.wait_for_timeout(250)

            celulas = linha_atual.locator("td").all()
            if len(celulas) < 8:
                logging.warning("Linha com estrutura inesperada, pulando.")
                continue
            
            dados_custas = {
                "sequencial": celulas[1].text_content().strip(),
                "especificacao": celulas[3].text_content().strip(),
                "situacao": celulas[4].text_content().strip(),
                "valor": celulas[6].text_content().strip(),
                "comprovante_pdf": "Não processado"
            }

            if "Efetivado/Liquidado" in dados_custas["situacao"]:
                logging.info(f"Custa '{dados_custas['sequencial']}' ({dados_custas['situacao']}) encontrada. Processando...")

                botao_detalhes = linha_atual.locator("button[bb-tooltip='Detalhes']")
                botao_detalhes.click()
                
                expect(page.locator("h3:has-text('Detalhar Custo')")).to_be_visible(timeout=20000)

                comprovantes_accordion = page.locator("div.accordion__item:has-text('Comprovantes')")
                
                try:
                    comprovantes_accordion.wait_for(state='visible', timeout=7000)
                    logging.info("Seção 'Comprovantes' encontrada.")

                    if 'is-open' not in (comprovantes_accordion.get_attribute('class') or ''):
                        logging.info("Expandindo seção 'Comprovantes'...")
                        comprovantes_accordion.locator(".accordion__title").click()

                    with page.context.expect_page() as new_page_info:
                        botao_emitir = comprovantes_accordion.locator("a[name='itensComprov']")
                        expect(botao_emitir).to_be_visible(timeout=5000)
                        botao_emitir.click()
                    
                    comprovante_page = new_page_info.value
                    comprovante_page.wait_for_load_state('domcontentloaded')

                    nome_base = f"comprovante_NPJ_{_limpar_nome_arquivo(npj)}_Custa_{dados_custas['sequencial']}_{_limpar_nome_arquivo(dados_custas['especificacao'])}_{_limpar_nome_arquivo(dados_custas['valor'])}.pdf"
                    caminho_pdf = COMPROVANTES_DIR / nome_base
                    
                    comprovante_page.pdf(path=caminho_pdf)
                    comprovante_page.close()
                    
                    dados_custas["comprovante_pdf"] = str(caminho_pdf)
                    logging.info(f"PDF do comprovante salvo em: {caminho_pdf}")

                except PlaywrightTimeoutError:
                    dados_custas["comprovante_pdf"] = "Não encontrado"
                    logging.warning("Seção 'Comprovantes' não encontrada ou não continha link para esta custa.")
                
                logging.info("Retornando para a lista de custas...")
                page.locator("button:has-text('Voltar')").click()
                expect(page.locator("h3:has-text('Solicitações de Custo')")).to_be_visible(timeout=20000)
                page.wait_for_timeout(1000)

            else:
                logging.info(f"Custa com situação '{dados_custas['situacao']}'. Pulando.")

            resultados_finais.append(dados_custas)

        return resultados_finais

    except Exception as e:
        logging.error(f"Ocorreu um erro crítico durante a extração: {e}", exc_info=True)
        screenshot_path = COMPROVANTES_DIR / f"erro_critico_{_limpar_nome_arquivo(npj)}.png"
        try:
            page.screenshot(path=screenshot_path, full_page=True)
            logging.error(f"Screenshot do erro salvo em: {screenshot_path}")
        except Exception as screenshot_error:
            logging.error(f"Falha ao tirar screenshot do erro: {screenshot_error}")
            
        return resultados_finais

