import logging
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional, Dict, List, Any
import json

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect

# Importar constantes do config
from config import COMPROVANTES_DIR, DOWNLOAD_TIMEOUT

# --- Funções Auxiliares ---
# (Funções _limpar_nome_arquivo, _converter_valor_para_decimal, _comparar_valores permanecem iguais)
def _limpar_nome_arquivo(nome: Any) -> str:
    """Remove caracteres inválidos e espaços de nomes de arquivos."""
    if not isinstance(nome, str):
        nome = str(nome)
    nome = nome.replace("R$", "").replace("/", "_").strip()
    nome = re.sub(r'[^\w\.\-]', '_', nome)
    nome = re.sub(r'_+', '_', nome)
    nome = nome.strip('_')
    return nome if nome else "arquivo"

def _converter_valor_para_decimal(valor_texto: Optional[str]) -> Optional[Decimal]:
    """Converte string formatada (ex: 'R$ 1.234,56') para Decimal."""
    if not valor_texto:
        return None
    try:
        valor_limpo = valor_texto.replace("R$", "").strip().replace(".", "").replace(",", ".")
        return Decimal(valor_limpo)
    except (InvalidOperation, ValueError):
        logging.error(f"Erro ao converter valor '{valor_texto}' para Decimal.")
        return None

def _comparar_valores(valor_bd: Optional[Decimal], valor_portal_texto: Optional[str]) -> bool:
    """Compara um Decimal do BD com uma string de valor do portal."""
    if valor_bd is None or valor_portal_texto is None:
        logging.debug(f"Comparação de valores falhou: Um dos valores é None (BD: {valor_bd}, Portal: {valor_portal_texto})")
        return False

    valor_portal_decimal = _converter_valor_para_decimal(valor_portal_texto)
    if valor_portal_decimal is None:
        logging.debug(f"Comparação de valores falhou: Falha ao converter valor do portal '{valor_portal_texto}' para Decimal.")
        return False

    comparacao = abs(valor_bd - valor_portal_decimal) < Decimal('0.001')
    logging.debug(f"Comparando Valor BD ({valor_bd}) com Valor Portal ({valor_portal_decimal}): {'Iguais' if comparacao else 'Diferentes'}")
    return comparacao
# --- Fim Funções Auxiliares ---


# --- Função Principal ---
def processar_solicitacao_especifica(page: Page, solicitacao_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processa uma solicitação de custa específica:
    1. Localiza a custa pelo NPJ, Nº Solicitação e Valor.
    2. Baixa comprovantes/documentos se status for 'Efetivado...' ou 'Efetivacao...'.
    3. Confirma a solicitação se status for 'Aguardando Confirmação'.
    4. Retorna o status final para a API (Pendente ou Finalizado).
    """
    npj_para_buscar = solicitacao_info.get("npj")
    solicitacao_id = solicitacao_info.get("id")
    num_solicitacao_bd = solicitacao_info.get("numero_solicitacao")
    try:
        valor_bd = Decimal(str(solicitacao_info.get("valor", "0.0")))
    except InvalidOperation:
        logging.error(f"Valor inválido na solicitação ID {solicitacao_id}: {solicitacao_info.get('valor')}. Usando 0.0.")
        valor_bd = Decimal("0.0")

    resultado_final = {
        "solicitacao_id": solicitacao_id,
        "numero_processo_completo": solicitacao_info.get("numero_processo"),
        "lista_arquivos_baixados": [], # <-- Vai armazenar caminhos relativos
        "status_portal_encontrado": None,
        "status_robo_final": "Erro: Falha não especificada", # Default
        "dados_custas_encontrados": {}
    }

    logging.info(f"Iniciando processamento para Solicitação ID: {solicitacao_id}, NPJ: {npj_para_buscar}")

    if not npj_para_buscar:
        logging.error("NPJ não fornecido para busca.")
        resultado_final["status_robo_final"] = "Erro: NPJ não fornecido"
        return resultado_final

    linha_alvo = None
    dados_custas_encontrados = {}
    numero_processo_completo = None

    try:
        # 1. Limpar Busca Anterior e Preencher NPJ
        logging.info("Verificando se está na página de consulta de custos...")
        try:
            page.wait_for_selector("button:has-text('Limpar'), input[placeholder='Informe o NPJ']", timeout=15000)
            logging.info("Página de consulta de custos confirmada.")
        except PlaywrightTimeoutError:
            logging.error("Não parece estar na página correta de consulta de custos.")
            raise ValueError("Página de consulta de custos não encontrada.")

        logging.info("Limpando formulário de busca anterior...")
        try:
            limpar_button = page.locator("button:has-text('Limpar')")
            limpar_button.wait_for(state='visible', timeout=5000)
            limpar_button.click()
            page.wait_for_timeout(500)
            logging.info("Formulário limpo via botão.")
        except PlaywrightTimeoutError:
             logging.warning("Botão 'Limpar' não encontrado, tentando limpar campo NPJ diretamente.")
             try:
                 input_npj_placeholder = page.locator("input[placeholder='Informe o NPJ']")
                 input_npj_placeholder.wait_for(state='visible', timeout=5000)
                 input_npj_placeholder.clear()
                 logging.info("Campo NPJ limpo diretamente.")
             except Exception as e_clear:
                  logging.error(f"Falha ao tentar limpar o campo NPJ: {e_clear}")

        input_npj = page.locator("#npj") # Usando ID #npj
        expect(input_npj).to_be_visible(timeout=10000)

        logging.info(f"Preenchendo NPJ: {npj_para_buscar}")
        input_npj.fill(npj_para_buscar)
        input_npj.press("Tab")

        # 2. Aguardar Tabela Carregar Automaticamente
        logging.info("Aguardando tabela de resultados carregar...")
        try:
            container_scroll = page.locator("div.tabs__pane.is-visible div[style*='overflow-y: auto']")
            expect(container_scroll).to_be_visible(timeout=20000)
            container_scroll.locator("tr[ng-repeat='item in $data']").first.wait_for(timeout=45000)
            logging.info("Tabela de resultados carregada.")
            page.wait_for_timeout(1500)
        except PlaywrightTimeoutError:
            logging.warning(f"Tabela não apareceu após preencher o NPJ {npj_para_buscar}.")
            resultado_final["status_robo_final"] = "Erro: Tabela de custos não encontrada"
            return resultado_final

        # 3. Encontrar a Custa Específica
        logging.info(f"Procurando custa com Nº Solicitação '{num_solicitacao_bd}' e Valor próximo a '{valor_bd}'...")
        todas_as_linhas = container_scroll.locator("tr[ng-repeat='item in $data']").all()

        if not todas_as_linhas:
            logging.warning(f"Nenhuma linha encontrada na tabela para o NPJ {npj_para_buscar}.")
            resultado_final["status_robo_final"] = "Erro: Nenhuma custa na tabela"
            return resultado_final

        for linha in todas_as_linhas:
            colunas = linha.locator("td").all()
            if len(colunas) < 7:
                logging.warning(f"Linha da tabela com {len(colunas)} colunas, pulando.")
                continue

            try:
                num_solicitacao_portal = colunas[1].inner_text().strip()
                valor_portal_texto = colunas[6].inner_text().strip()
                status_portal = colunas[4].inner_text().strip()
                especificacao_portal = colunas[3].inner_text().strip()

                logging.debug(f"Linha encontrada: Nº Sol: {num_solicitacao_portal}, Valor: {valor_portal_texto}, Status: {status_portal}")

                if num_solicitacao_portal == num_solicitacao_bd and _comparar_valores(valor_bd, valor_portal_texto):
                    logging.info(f"Custa correspondente (Nº Sol e Valor) encontrada! Status: '{status_portal}'")
                    linha_alvo = linha
                    resultado_final["status_portal_encontrado"] = status_portal
                    dados_custas_encontrados = {
                         "numero_solicitacao": num_solicitacao_portal,
                         "valor": valor_portal_texto,
                         "status": status_portal,
                         "especificacao": especificacao_portal
                    }
                    resultado_final["dados_custas_encontrados"] = dados_custas_encontrados
                    break

            except Exception as e_linha:
                logging.error(f"Erro ao ler dados da linha: {e_linha}")
                continue

        if not linha_alvo:
            logging.warning(f"Nenhuma custa correspondente a Nº Sol '{num_solicitacao_bd}' e Valor '{valor_bd}' encontrada.")
            resultado_final["status_robo_final"] = "Erro: Custa específica não encontrada"
            return resultado_final

        # 4. Processar a Linha Encontrada
        status_portal = resultado_final["status_portal_encontrado"]
        lista_arquivos_baixados_custa = []

        status_de_conclusao = [
            "Efetivado/Liquidado",
            "Efetivacao aguardando processamento EVT"
        ]
        status_de_confirmacao = [
            "Aguardando Confirmação"
        ]
        
        if any(s.lower() in status_portal.lower() for s in status_de_conclusao):
            logging.info(f"Status '{status_portal}' é de conclusão. Iniciando fluxo de download...")

            npj_limpo = _limpar_nome_arquivo(npj_para_buscar)
            # ---> MUDANÇA: O diretório base é COMPROVANTES_DIR <---
            diretorio_npj = COMPROVANTES_DIR / npj_limpo
            diretorio_npj.mkdir(parents=True, exist_ok=True)
            logging.info(f"Diretório para arquivos: {diretorio_npj}")

            botao_detalhes = linha_alvo.locator("button[bb-tooltip='Detalhes']")
            botao_detalhes.wait_for(state='visible', timeout=5000)
            botao_detalhes.click()
            logging.info("Botão 'Detalhes' clicado.")

            logging.info("Aguardando página de detalhes...")
            page.locator("div.loader.is-loading").wait_for(state="hidden", timeout=30000)
            expect(page.locator("h3:has-text('Detalhar Custo')")).to_be_visible(timeout=20000)
            logging.info("Página de detalhes carregada.")

            try:
                 processo_chip_desc = page.locator('div[bb-title="Processo"] span.chip__desc').first
                 processo_chip_desc.wait_for(state='visible', timeout=5000)
                 numero_processo_completo = processo_chip_desc.inner_text().strip()
                 if numero_processo_completo:
                      logging.info(f"Número do Processo extraído: {numero_processo_completo}")
                      resultado_final["numero_processo_completo"] = numero_processo_completo
                 else: logging.warning("Elemento do número do processo encontrado, mas vazio.")
            except PlaywrightTimeoutError: logging.warning("Não foi possível encontrar o elemento do número do processo.")
            except Exception as e: logging.error(f"Erro ao extrair número do processo: {e}")

            num_proc_para_nome = _limpar_nome_arquivo(numero_processo_completo or npj_para_buscar)
            valor_custo_str = dados_custas_encontrados.get('valor', '0')
            espec_custo = dados_custas_encontrados.get('especificacao', 'Desconhecida')

            # Baixar Comprovante(s)
            try:
                comprovantes_accordion = page.locator("div.accordion__item:has-text('Comprovantes')")
                comprovantes_accordion.wait_for(state='visible', timeout=7000)
                if 'is-open' not in (comprovantes_accordion.get_attribute('class') or ''):
                    comprovantes_accordion.locator(".accordion__title").click()
                    comprovantes_accordion.locator("table").wait_for(state='visible', timeout=10000)
                botoes_emitir = comprovantes_accordion.locator("a[name='itensComprov']").all()
                logging.info(f"Encontrados {len(botoes_emitir)} comprovante(s) para baixar.")
                for i, botao in enumerate(botoes_emitir):
                    with page.context.expect_page(timeout=20000) as new_page_info:
                        botao.click()
                    comprovante_page = new_page_info.value
                    comprovante_page.wait_for_load_state('domcontentloaded', timeout=30000)
                    comprovante_page.wait_for_timeout(2000)
                    nome_original_comprovante = f"Comprovante_{i+1}"
                    nome_arquivo_comprovante = f"{_limpar_nome_arquivo(nome_original_comprovante)}_{num_proc_para_nome}_{_limpar_nome_arquivo(num_solicitacao_bd)}_{_limpar_nome_arquivo(valor_custo_str)}.pdf"
                    caminho_pdf_completo = diretorio_npj / nome_arquivo_comprovante
                    
                    logging.info(f"Salvando comprovante {i+1} PDF em: {caminho_pdf_completo}")
                    comprovante_page.pdf(path=str(caminho_pdf_completo))
                    comprovante_page.close()
                    
                    # ---> MUDANÇA: Salvar caminho relativo <---
                    caminho_relativo = caminho_pdf_completo.relative_to(COMPROVANTES_DIR)
                    lista_arquivos_baixados_custa.append(caminho_relativo.as_posix()) # as_posix() usa '/'
                    
                    logging.info(f"Comprovante {i+1} salvo. Caminho relativo: {caminho_relativo.as_posix()}")
                    
            except PlaywrightTimeoutError: logging.warning("Seção 'Comprovantes' não encontrada ou timeout.")
            except Exception as e_comp: logging.error(f"Erro ao baixar comprovante(s): {e_comp}", exc_info=True)

            # Baixar Documentos Geradores
            logging.info("Procurando seção 'Documentos do Custo'...")
            try:
                documentos_section = page.locator("div.accordion__item[bb-item-title='Documentos do Custo']")
                documentos_section.wait_for(state='visible', timeout=5000)
                if 'is-open' not in (documentos_section.get_attribute('class') or ''):
                    logging.info("Abrindo seção 'Documentos do Custo'...")
                    documentos_section.locator(".accordion__title").click()
                    documentos_section.locator("table").wait_for(state='visible', timeout=10000)
                links_download_docs = documentos_section.locator("td a[href*='/paj/resources/app/v0/processo/documento/download/']").all()
                if not links_download_docs: logging.info("Nenhum documento gerador encontrado.")
                else:
                    logging.info(f"Encontrados {len(links_download_docs)} documentos geradores para baixar.")
                    for i, link_doc in enumerate(links_download_docs):
                        try:
                            nome_original_doc = f"DocumentoGerador_{i+1}"
                            try:
                                linha_tr = link_doc.locator("xpath=ancestor::tr")
                                nome_td_span = linha_tr.locator("td:first-child span").first
                                nome_td_span.wait_for(state='visible', timeout=2000)
                                nome_temp = nome_td_span.inner_text().strip()
                                if nome_temp: nome_original_doc = nome_temp
                            except Exception: logging.warning(f"Não foi possível extrair nome original do documento {i+1}, usando fallback.")
                            
                            ext = ".pdf"; nome_original_doc_sem_ext = nome_original_doc
                            if '.' in nome_original_doc:
                                 ext = Path(nome_original_doc).suffix or ".pdf"
                                 nome_original_doc_sem_ext = Path(nome_original_doc).stem

                            nome_arquivo_doc = f"{_limpar_nome_arquivo(nome_original_doc_sem_ext)}_{num_proc_para_nome}_{_limpar_nome_arquivo(num_solicitacao_bd)}_{_limpar_nome_arquivo(valor_custo_str)}{ext}"
                            caminho_arquivo_doc_completo = diretorio_npj / nome_arquivo_doc
                            
                            logging.info(f"Iniciando download doc {i+1}: '{nome_original_doc}' para '{caminho_arquivo_doc_completo}'...")
                            with page.expect_download(timeout=DOWNLOAD_TIMEOUT) as download_info:
                                link_doc.click()
                            download = download_info.value
                            suggested_filename = download.suggested_filename
                            if suggested_filename and '.' in suggested_filename:
                                 actual_ext = Path(suggested_filename).suffix
                                 if actual_ext.lower() != ext.lower():
                                      logging.info(f"Ajustando extensão para '{actual_ext}' baseado no download.")
                                      ext = actual_ext
                                      nome_arquivo_doc = f"{_limpar_nome_arquivo(nome_original_doc_sem_ext)}_{num_proc_para_nome}_{_limpar_nome_arquivo(num_solicitacao_bd)}_{_limpar_nome_arquivo(valor_custo_str)}{ext}"
                                      caminho_arquivo_doc_completo = diretorio_npj / nome_arquivo_doc
                                      
                            download.save_as(caminho_arquivo_doc_completo)
                            
                            # ---> MUDANÇA: Salvar caminho relativo <---
                            caminho_relativo_doc = caminho_arquivo_doc_completo.relative_to(COMPROVANTES_DIR)
                            lista_arquivos_baixados_custa.append(caminho_relativo_doc.as_posix())
                            
                            logging.info(f"Download doc {i+1} concluído. Caminho relativo: {caminho_relativo_doc.as_posix()}")
                            time.sleep(1)
                        except PlaywrightTimeoutError as e_down_timeout: logging.error(f"Timeout ao baixar doc {i+1} ('{nome_original_doc}'): {e_down_timeout}")
                        except Exception as e_down: logging.error(f"Erro ao baixar doc {i+1} ('{nome_original_doc}'): {e_down}", exc_info=True)
            except PlaywrightTimeoutError: logging.warning("Seção 'Documentos do Custo' não encontrada.")
            except Exception as e_docs: logging.error(f"Erro ao processar docs geradores: {e_docs}", exc_info=True)

            finally:
                logging.info("Tentando voltar para a lista de custos...")
                try:
                    page.locator("button:has-text('Voltar')").click()
                    expect(page.locator("h3:has-text('Solicitações de Custo')")).to_be_visible(timeout=20000)
                    page.wait_for_timeout(1000)
                    logging.info("Retornou para a lista de custos.")
                except Exception as e_voltar:
                     logging.error(f"Erro ao voltar para a lista: {e_voltar}")

            if not lista_arquivos_baixados_custa:
                 resultado_final["status_robo_final"] = f"Finalizado: Nenhum Arquivo Baixado (Status Portal: {status_portal})"
            else:
                 resultado_final["status_robo_final"] = "Finalizado com Sucesso"

        elif any(s.lower() in status_portal.lower() for s in status_de_confirmacao):
            logging.info(f"Status '{status_portal}'. Iniciando fluxo de confirmação.")
            
            botao_confirmar = linha_alvo.locator("button[bb-tooltip='Confirmar/Efetivar']")
            botao_confirmar.click()
            logging.info("Aguardando tela de despacho carregar...")
            page.locator("div.loader.is-loading").wait_for(state="hidden", timeout=30000)
            expect(page.locator("h3:has-text('DADOS DA SOLICITAÇÃO')")).to_be_visible(timeout=20000)
            logging.info("Página de despacho carregada.")
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
            
            # Conforme solicitado: volta para Pendente para re-verificação
            resultado_final["status_robo_final"] = "Pendente"
            logging.info("Status da solicitação será definido como 'Pendente' para re-verificação futura.")

        else:
            logging.info(f"Status do portal é '{status_portal}'. Nenhuma ação automática definida.")
            # Conforme solicitado: mantém como Pendente para re-verificação
            resultado_final["status_robo_final"] = "Pendente"
            logging.info(f"Status da solicitação será mantido/definido como 'Pendente' para re-verificação. Status portal '{status_portal}' foi registrado.")

        resultado_final["lista_arquivos_baixados"] = lista_arquivos_baixados_custa

    except PlaywrightTimeoutError as e:
        logging.error(f"Timeout durante processamento ID {solicitacao_id}: {e}", exc_info=True)
        resultado_final["status_robo_final"] = f"Erro: Timeout Playwright"
        try:
             npj_dir_erro = _limpar_nome_arquivo(npj_para_buscar if npj_para_buscar else "ERRO_SEM_NPJ")
             screenshot_path_completo = Path(COMPROVANTES_DIR) / npj_dir_erro / f"erro_timeout_{solicitacao_id}.png"
             screenshot_path_completo.parent.mkdir(parents=True, exist_ok=True)
             page.screenshot(path=str(screenshot_path_completo))
             logging.info(f"Screenshot salvo em: {screenshot_path_completo}")
             # ---> MUDANÇA: Salvar caminho relativo <---
             screenshot_relativo = screenshot_path_completo.relative_to(COMPROVANTES_DIR)
             resultado_final["lista_arquivos_baixados"].append(screenshot_relativo.as_posix())
        except Exception as e_screen: logging.error(f"Falha ao salvar screenshot: {e_screen}")

    except Exception as e:
        logging.exception(f"Erro crítico durante processamento ID {solicitacao_id}")
        resultado_final["status_robo_final"] = f"Erro Crítico: {type(e).__name__}"
        try:
             npj_dir_erro = _limpar_nome_arquivo(npj_para_buscar if npj_para_buscar else "ERRO_SEM_NPJ")
             screenshot_path_completo = Path(COMPROVANTES_DIR) / npj_dir_erro / f"erro_critico_{solicitacao_id}.png"
             screenshot_path_completo.parent.mkdir(parents=True, exist_ok=True)
             page.screenshot(path=str(screenshot_path_completo))
             logging.info(f"Screenshot salvo em: {screenshot_path_completo}")
             # ---> MUDANÇA: Salvar caminho relativo <---
             screenshot_relativo = screenshot_path_completo.relative_to(COMPROVANTES_DIR)
             resultado_final["lista_arquivos_baixados"].append(screenshot_relativo.as_posix())
        except Exception as e_screen: logging.error(f"Falha ao salvar screenshot: {e_screen}")

    logging.info(f"Processamento finalizado para ID {solicitacao_id}. Status Robô final: '{resultado_final['status_robo_final']}'. Arquivos: {len(resultado_final['lista_arquivos_baixados'])}.")
    return resultado_final

