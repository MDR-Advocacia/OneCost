import logging
import re
from playwright.sync_api import Page, expect, TimeoutError as PlaywrightTimeoutError
from typing import Dict, Any

from config import COMPROVANTES_DIR

def _limpar_nome_arquivo(texto: str) -> str:
    """Remove caracteres inválidos de uma string para usar como nome de arquivo."""
    texto = texto.replace('R$', '').strip()
    return re.sub(r'[\\/*?:"<>|]', '_', texto)

def processar_solicitacao_especifica(page: Page, solicitacao: Dict[str, Any]) -> Dict[str, Any]:
    """
    Busca um NPJ específico, encontra a custa pelo número da solicitação e
    processa apenas essa custa, baixando comprovantes ou confirmando a solicitação.
    """
    npj = solicitacao["npj"]
    num_solicitacao_alvo = solicitacao["numero_solicitacao"]
    resultado_update = {}
    
    logging.info(f"Processando NPJ '{npj}', alvo: solicitação nº '{num_solicitacao_alvo}'")

    try:
        # 1. Pesquisa pelo NPJ
        
        # --- CORREÇÃO: Clicar em "Limpar" ---
        # Em vez de input_npj.clear(), clicamos no botão "Limpar"
        # para garantir que o formulário seja resetado pelo framework.
        logging.info("Limpando formulário de busca anterior...")
        page.locator("button:has-text('Limpar')").click()
        page.wait_for_timeout(500) # Pequena pausa para o JS limpar o campo

        input_npj = page.locator("#npj")
        expect(input_npj).to_be_visible(timeout=20000)
        
        # Agora preenche o campo
        input_npj.fill(npj)
        input_npj.press("Tab")
        
        container_scroll = page.locator("div.tabs__pane.is-visible div[style*='overflow-y: auto']")
        expect(container_scroll).to_be_visible(timeout=20000)
        
        container_scroll.locator("tr[ng-repeat='item in $data']").first.wait_for(timeout=15000)
        page.wait_for_timeout(1500)

        # 2. Encontra a linha correta na tabela
        todas_as_linhas = container_scroll.locator("tr[ng-repeat='item in $data']").all()
        linha_alvo = None
        
        for linha in todas_as_linhas:
            num_solicitacao_na_linha = linha.locator("td").nth(1).text_content().strip()
            if num_solicitacao_na_linha == num_solicitacao_alvo:
                linha_alvo = linha
                break
        
        if not linha_alvo:
            logging.warning(f"Não foi encontrada a custa com número de solicitação '{num_solicitacao_alvo}' para o NPJ '{npj}'.")
            resultado_update["status_robo"] = "Erro: Custa não encontrada no portal"
            return resultado_update

        logging.info("Custa correspondente encontrada na tabela.")
        
        # 3. Extrai dados e processa a linha encontrada
        celulas = linha_alvo.locator("td").all()
        status_portal = celulas[4].text_content().strip()
        resultado_update["status_portal"] = status_portal
        
        # --- Lógica de Ação ---
        
        if "Efetivado/Liquidado" in status_portal:
            logging.info("Status 'Efetivado/Liquidado'. Tentando baixar comprovante...")
            
            botao_detalhes = linha_alvo.locator("button[bb-tooltip='Detalhes']")
            botao_detalhes.click()

            # Espera o loader da tela de detalhes desaparecer
            page.locator("div.loader.is-loading").wait_for(state="hidden", timeout=30000)
            
            expect(page.locator("h3:has-text('Detalhar Custo')")).to_be_visible(timeout=20000)

            try:
                comprovantes_accordion = page.locator("div.accordion__item:has-text('Comprovantes')")
                comprovantes_accordion.wait_for(state='visible', timeout=7000)

                if 'is-open' not in (comprovantes_accordion.get_attribute('class') or ''):
                    comprovantes_accordion.locator(".accordion__title").click()

                comprovantes_paths = []
                botoes_emitir = comprovantes_accordion.locator("a[name='itensComprov']").all()

                for i, botao in enumerate(botoes_emitir):
                    with page.context.expect_page() as new_page_info:
                        botao.click()
                    
                    comprovante_page = new_page_info.value
                    comprovante_page.wait_for_load_state('domcontentloaded')
                    
                    valor_custo = celulas[6].text_content().strip()
                    espec_custo = celulas[3].text_content().strip()
                    
                    nome_base = f"comprovante_NPJ_{_limpar_nome_arquivo(npj)}_Custa_{num_solicitacao_alvo}_{_limpar_nome_arquivo(espec_custo)}_{_limpar_nome_arquivo(valor_custo)}"
                    sufixo = f"_({i+1})" if len(botoes_emitir) > 1 else ""
                    caminho_pdf = COMPROVANTES_DIR / f"{nome_base}{sufixo}.pdf"
                    
                    comprovante_page.pdf(path=caminho_pdf)
                    comprovante_page.close()
                    
                    comprovantes_paths.append(str(caminho_pdf))
                    logging.info(f"Comprovante {i+1} salvo em: {caminho_pdf}")

                resultado_update["comprovantes_path"] = ",".join(comprovantes_paths)
                resultado_update["status_robo"] = "Finalizado com Sucesso"

            except PlaywrightTimeoutError:
                logging.warning("Não foi possível encontrar/baixar o comprovante.")
                resultado_update["status_robo"] = "Erro: Comprovante não encontrado"
            
            finally:
                page.locator("button:has-text('Voltar')").click()
                expect(page.locator("h3:has-text('Solicitações de Custo')")).to_be_visible(timeout=20000)
                page.wait_for_timeout(1000)

        elif "Aguardando Confirmação" in status_portal:
            logging.info("Status 'Aguardando Confirmação'. Iniciando fluxo de confirmação.")
            
            botao_confirmar = linha_alvo.locator("button[bb-tooltip='Confirmar/Efetivar']")
            botao_confirmar.click()

            logging.info("Aguardando tela de despacho carregar...")
            page.locator("div.loader.is-loading").wait_for(state="hidden", timeout=30000)

            expect(page.locator("h3:has-text('DADOS DA SOLICITAÇÃO')")).to_be_visible(timeout=20000)
            logging.info("Página de despacho carregada.")

            # CORREÇÃO (feita por você): Clicar diretamente no elemento que contém o texto "Aprovar".
            page.locator("label.form-radio.form-inline span:has-text('Aprovar')").click()
            logging.info("Opção 'Aprovar' selecionada.")
            
            botao_salvar = page.locator("button:has-text('Salvar')")
            expect(botao_salvar).to_be_enabled(timeout=5000)
            botao_salvar.click()
            logging.info("Botão 'Salvar' clicado.")
            
            logging.info("Aguardando confirmação do salvamento...")
            page.locator("div.loader.is-loading").wait_for(state="hidden", timeout=30000)
            
            expect(page.locator("h3:has-text('Solicitações de Custo')")).to_be_visible(timeout=30000)
            logging.info("Confirmação realizada com sucesso. Retornou para a lista.")
            page.wait_for_timeout(1500)
            
            resultado_update["status_robo"] = "Finalizado (Confirmação Realizada)"
            
        else:
            logging.info(f"Status do portal é '{status_portal}'. Nenhuma ação automática definida para este status.")
            resultado_update["status_robo"] = "Finalizado (Status não processável)"

    except PlaywrightTimeoutError as e:
        logging.error(f"Timeout ao processar a solicitação {num_solicitacao_alvo} para o NPJ {npj}: {e}")
        resultado_update["status_robo"] = "Erro: Timeout na automação"
    except Exception as e:
        logging.critical(f"Erro inesperado ao processar a solicitação {num_solicitacao_alvo} para o NPJ {npj}: {e}", exc_info=True)
        resultado_update["status_robo"] = f"Erro: {str(e)}"

    return resultado_update

