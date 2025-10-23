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
# NOVO: Importar o ID do usuário robô (preenchido após o login)
from utils.api_client import _robot_user_id

# --- Funções Auxiliares ---
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

    # Compara com uma pequena tolerância para evitar problemas de arredondamento
    comparacao = abs(valor_bd - valor_portal_decimal) < Decimal('0.001')
    logging.debug(f"Comparando Valor BD ({valor_bd}) com Valor Portal ({valor_portal_decimal}): {'Iguais' if comparacao else 'Diferentes'}")
    return comparacao
# --- Fim Funções Auxiliares ---


# --- Função Principal ---
def processar_solicitacao_especifica(page: Page, solicitacao_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processa uma solicitação de custa específica:
    1. Localiza a custa pelo NPJ, Nº Solicitação e Valor.
    2. Baixa comprovantes/documentos se status for de conclusão.
    3. Confirma a solicitação se status for 'Aguardando Confirmação' e REVERIFICA o status.
    4. Retorna dados atualizados para a API (status, arquivos, ID de confirmação).
    """
    npj_para_buscar = solicitacao_info.get("npj")
    solicitacao_id = solicitacao_info.get("id")
    num_solicitacao_bd = solicitacao_info.get("numero_solicitacao")
    try:
        valor_bd = Decimal(str(solicitacao_info.get("valor", "0.0")))
    except InvalidOperation:
        logging.error(f"Valor inválido na solicitação ID {solicitacao_id}: {solicitacao_info.get('valor')}. Usando 0.0.")
        valor_bd = Decimal("0.0")

    # Estrutura do resultado a ser retornado para a API
    resultado_final = {
        "solicitacao_id": solicitacao_id,
        "numero_processo_completo": solicitacao_info.get("numero_processo"), # Pode ser atualizado
        "lista_arquivos_baixados": [], # Caminhos relativos
        "status_portal_encontrado": None, # Status lido do portal
        "status_robo_final": "Erro: Falha não especificada", # Status final para o OneCost
        "usuario_confirmacao_id": None, # NOVO: ID do robô se ele confirmar
        "dados_custas_encontrados": {} # Dados lidos da linha da tabela
    }

    logging.info(f"Iniciando processamento para Solicitação ID: {solicitacao_id}, NPJ: {npj_para_buscar}")

    if not npj_para_buscar:
        logging.error(f"NPJ não fornecido para busca na solicitação ID {solicitacao_id}.")
        resultado_final["status_robo_final"] = "Erro: NPJ não fornecido"
        return resultado_final

    linha_alvo = None
    dados_custas_encontrados = {}
    numero_processo_completo = None

    try:
        # 1. Garantir que está na página certa e Limpar Busca
        logging.info("Verificando página de consulta e limpando busca anterior...")
        try:
            # Espera por um elemento chave da página de consulta
            page.wait_for_selector("input#npj, button:has-text('Limpar')", timeout=20000)
            logging.info("Página de consulta de custos confirmada.")

            # Tenta limpar o formulário
            limpar_button = page.locator("button:has-text('Limpar')")
            limpar_button.wait_for(state='visible', timeout=7000)
            limpar_button.click()
            page.wait_for_timeout(500) # Pequena pausa após limpar
            logging.info("Formulário limpo.")
        except PlaywrightTimeoutError:
            logging.warning("Botão 'Limpar' não encontrado ou página incorreta. Tentando continuar...")
            # Tenta limpar campo NPJ diretamente se botão falhar
            try:
                input_npj_placeholder = page.locator("input[placeholder='Informe o NPJ']")
                input_npj_placeholder.wait_for(state='visible', timeout=5000)
                input_npj_placeholder.clear()
                logging.info("Campo NPJ limpo diretamente.")
            except Exception as e_clear_input:
                logging.error(f"Falha ao tentar limpar o campo NPJ diretamente: {e_clear_input}")
                # Considerar lançar erro aqui se a limpeza for crítica
        except Exception as e_clear:
            logging.error(f"Erro ao tentar limpar o formulário: {e_clear}")

        # 2. Preencher NPJ e Aguardar Tabela
        input_npj = page.locator("#npj")
        expect(input_npj).to_be_visible(timeout=15000)
        logging.info(f"Preenchendo NPJ: {npj_para_buscar}")
        input_npj.fill(npj_para_buscar)
        input_npj.press("Tab") # Ajuda a disparar eventos
        page.wait_for_timeout(500) # Pausa antes de esperar a tabela

        logging.info("Aguardando tabela de resultados carregar...")
        try:
            # Localizador mais específico para o container da tabela visível
            container_scroll = page.locator("div.tabs__pane.is-visible div[style*='overflow-y: auto']")
            expect(container_scroll).to_be_visible(timeout=30000)
            # Espera pela primeira linha de dados na tabela
            container_scroll.locator("tr[ng-repeat='item in $data']").first.wait_for(timeout=60000)
            logging.info("Tabela de resultados carregada.")
            page.wait_for_timeout(1500) # Pausa extra para garantir renderização
        except PlaywrightTimeoutError:
            logging.warning(f"Tabela de custos não apareceu após preencher o NPJ {npj_para_buscar}.")
            resultado_final["status_robo_final"] = "Erro: Tabela de custos não encontrada"
            return resultado_final

        # 3. Encontrar a Custa Específica na Tabela
        logging.info(f"Procurando custa com Nº Solicitação '{num_solicitacao_bd}' e Valor próximo a '{valor_bd}'...")
        todas_as_linhas = container_scroll.locator("tr[ng-repeat='item in $data']").all()

        if not todas_as_linhas:
            logging.warning(f"Nenhuma linha encontrada na tabela para o NPJ {npj_para_buscar}.")
            resultado_final["status_robo_final"] = "Erro: Nenhuma custa na tabela"
            return resultado_final

        for linha in todas_as_linhas:
            try:
                colunas = linha.locator("td").all()
                if len(colunas) < 7: continue # Pula linhas incompletas

                num_solicitacao_portal = colunas[1].inner_text(timeout=2000).strip()
                valor_portal_texto = colunas[6].inner_text(timeout=2000).strip()
                status_portal = colunas[4].inner_text(timeout=2000).strip()
                especificacao_portal = colunas[3].inner_text(timeout=2000).strip()

                logging.debug(f"Linha lida: Nº Sol: {num_solicitacao_portal}, Valor: {valor_portal_texto}, Status: {status_portal}")

                # Compara número da solicitação e valor (com tolerância)
                if num_solicitacao_portal == num_solicitacao_bd and _comparar_valores(valor_bd, valor_portal_texto):
                    logging.info(f"Custa correspondente (ID {solicitacao_id}) encontrada! Status Portal: '{status_portal}'")
                    linha_alvo = linha
                    resultado_final["status_portal_encontrado"] = status_portal
                    dados_custas_encontrados = {
                         "numero_solicitacao": num_solicitacao_portal,
                         "valor": valor_portal_texto,
                         "status": status_portal,
                         "especificacao": especificacao_portal
                    }
                    resultado_final["dados_custas_encontrados"] = dados_custas_encontrados
                    break # Encontrou a linha, sai do loop

            except Exception as e_linha:
                logging.error(f"Erro ao processar linha da tabela: {e_linha}", exc_info=True)
                continue # Tenta a próxima linha

        if not linha_alvo:
            logging.warning(f"Nenhuma custa correspondente a Nº Sol '{num_solicitacao_bd}' e Valor '{valor_bd}' encontrada para NPJ {npj_para_buscar}.")
            resultado_final["status_robo_final"] = "Erro: Custa específica não encontrada"
            return resultado_final

        # 4. Processar a Linha Encontrada com Base no Status
        status_portal_inicial = resultado_final["status_portal_encontrado"] # Guarda o status inicial
        lista_arquivos_baixados_custa = [] # Lista para esta custa específica

        # Status que indicam que a custa foi paga/finalizada no portal
        status_de_conclusao = [
            "Efetivado/Liquidado",
            "Efetivacao aguardando processamento EVT"
        ]
        # Status que requer ação de confirmação do robô
        status_de_confirmacao = [
            "Aguardando Confirmação"
        ]

        # --- AÇÃO: Baixar Comprovantes ---
        if any(s.lower() in status_portal_inicial.lower() for s in status_de_conclusao):
            logging.info(f"Status '{status_portal_inicial}' indica conclusão. Iniciando download de documentos...")

            # Cria diretório para os arquivos (baseado no NPJ)
            npj_limpo = _limpar_nome_arquivo(npj_para_buscar)
            diretorio_npj = COMPROVANTES_DIR / npj_limpo
            diretorio_npj.mkdir(parents=True, exist_ok=True)
            logging.info(f"Diretório para arquivos: {diretorio_npj}")

            # Clica em Detalhes
            botao_detalhes = linha_alvo.locator("button[bb-tooltip='Detalhes']")
            expect(botao_detalhes).to_be_visible(timeout=10000)
            botao_detalhes.click()
            logging.info("Botão 'Detalhes' clicado.")

            # Aguarda página de detalhes carregar
            logging.info("Aguardando página de detalhes...")
            page.locator("div.loader.is-loading").wait_for(state="hidden", timeout=45000)
            expect(page.locator("h3:has-text('Detalhar Custo')")).to_be_visible(timeout=30000)
            logging.info("Página de detalhes carregada.")
            page.wait_for_timeout(1000) # Pausa extra

            # Tenta extrair número completo do processo
            try:
                 processo_chip_desc = page.locator('div[bb-title="Processo"] span.chip__desc').first
                 processo_chip_desc.wait_for(state='visible', timeout=7000)
                 numero_processo_completo = processo_chip_desc.inner_text().strip()
                 if numero_processo_completo:
                      logging.info(f"Número do Processo completo extraído: {numero_processo_completo}")
                      resultado_final["numero_processo_completo"] = numero_processo_completo # Atualiza o resultado
                 else: logging.warning("Elemento do número do processo encontrado, mas estava vazio.")
            except PlaywrightTimeoutError: logging.warning("Não foi possível encontrar/ler o elemento do número do processo completo.")
            except Exception as e: logging.error(f"Erro ao extrair número do processo completo: {e}")

            # Define partes do nome do arquivo
            num_proc_para_nome = _limpar_nome_arquivo(numero_processo_completo or npj_para_buscar)
            valor_custo_str = dados_custas_encontrados.get('valor', '0')
            espec_custo = dados_custas_encontrados.get('especificacao', 'Desconhecida')

            # --- Baixar Comprovante(s) PDF ---
            try:
                comprovantes_accordion = page.locator("div.accordion__item:has-text('Comprovantes')")
                comprovantes_accordion.wait_for(state='visible', timeout=10000)
                if 'is-open' not in (comprovantes_accordion.get_attribute('class', timeout=1000) or ''):
                    comprovantes_accordion.locator(".accordion__title").click()
                    comprovantes_accordion.locator("table").wait_for(state='visible', timeout=10000)

                botoes_emitir = comprovantes_accordion.locator("a[name='itensComprov']").all()
                logging.info(f"Encontrados {len(botoes_emitir)} comprovante(s) PDF para baixar.")
                for i, botao in enumerate(botoes_emitir):
                    nome_original_comprovante = f"Comprovante_{i+1}"
                    try:
                        tooltip = botao.get_attribute('bb-tooltip')
                        if tooltip: nome_original_comprovante = tooltip
                    except: pass

                    with page.context.expect_page(timeout=25000) as new_page_info:
                        botao.click()
                    comprovante_page = new_page_info.value
                    comprovante_page.wait_for_load_state('domcontentloaded', timeout=40000)
                    comprovante_page.wait_for_timeout(2000)

                    nome_arquivo_comprovante = f"{_limpar_nome_arquivo(nome_original_comprovante)}_{num_proc_para_nome}_{_limpar_nome_arquivo(num_solicitacao_bd)}_{_limpar_nome_arquivo(valor_custo_str)}.pdf"
                    caminho_pdf_completo = diretorio_npj / nome_arquivo_comprovante

                    logging.info(f"Salvando comprovante PDF {i+1} em: {caminho_pdf_completo}")
                    comprovante_page.pdf(path=str(caminho_pdf_completo))
                    comprovante_page.close()

                    caminho_relativo = caminho_pdf_completo.relative_to(COMPROVANTES_DIR)
                    lista_arquivos_baixados_custa.append(caminho_relativo.as_posix())
                    logging.info(f"Comprovante PDF {i+1} salvo. Caminho relativo: {caminho_relativo.as_posix()}")

            except PlaywrightTimeoutError: logging.warning("Seção 'Comprovantes' ou botão/tabela não encontrados ou timeout.")
            except Exception as e_comp: logging.error(f"Erro ao baixar comprovante(s) PDF: {e_comp}", exc_info=True)

            # --- Baixar Documentos Geradores ---
            logging.info("Procurando seção 'Documentos do Custo'...")
            try:
                documentos_section = page.locator("div.accordion__item[bb-item-title='Documentos do Custo']")
                documentos_section.wait_for(state='visible', timeout=10000)
                if 'is-open' not in (documentos_section.get_attribute('class', timeout=1000) or ''):
                    logging.info("Abrindo seção 'Documentos do Custo'...")
                    documentos_section.locator(".accordion__title").click()
                    documentos_section.locator("table").wait_for(state='visible', timeout=10000)

                links_download_docs = documentos_section.locator("td a[href*='/paj/resources/app/v0/processo/documento/download/']").all()

                if not links_download_docs: logging.info("Nenhum documento gerador encontrado nesta seção.")
                else:
                    logging.info(f"Encontrados {len(links_download_docs)} documento(s) gerador(es) para baixar.")
                    for i, link_doc in enumerate(links_download_docs):
                        nome_original_doc = f"DocumentoGerador_{i+1}"
                        try:
                            linha_tr = link_doc.locator("xpath=ancestor::tr")
                            nome_td_span = linha_tr.locator("td:first-child span").first
                            nome_td_span.wait_for(state='visible', timeout=3000)
                            nome_temp = nome_td_span.inner_text().strip()
                            if nome_temp: nome_original_doc = nome_temp
                        except Exception: logging.warning(f"Não foi possível extrair nome original do documento {i+1}, usando fallback.")

                        try:
                            logging.info(f"Iniciando download doc {i+1}: '{nome_original_doc}'...")
                            with page.expect_download(timeout=DOWNLOAD_TIMEOUT) as download_info:
                                link_doc.click()
                            download = download_info.value

                            suggested_filename = download.suggested_filename
                            ext = Path(suggested_filename).suffix or ".pdf"
                            nome_original_doc_sem_ext = Path(nome_original_doc).stem
                            nome_arquivo_doc = f"{_limpar_nome_arquivo(nome_original_doc_sem_ext)}_{num_proc_para_nome}_{_limpar_nome_arquivo(num_solicitacao_bd)}_{_limpar_nome_arquivo(valor_custo_str)}{ext}"
                            caminho_arquivo_doc_completo = diretorio_npj / nome_arquivo_doc

                            download.save_as(caminho_arquivo_doc_completo)

                            caminho_relativo_doc = caminho_arquivo_doc_completo.relative_to(COMPROVANTES_DIR)
                            lista_arquivos_baixados_custa.append(caminho_relativo_doc.as_posix())

                            logging.info(f"Download doc {i+1} ('{suggested_filename}') concluído. Caminho relativo: {caminho_relativo_doc.as_posix()}")
                            time.sleep(1)

                        except PlaywrightTimeoutError as e_down_timeout: logging.error(f"Timeout ao esperar download do doc {i+1} ('{nome_original_doc}'): {e_down_timeout}")
                        except Exception as e_down: logging.error(f"Erro durante download ou salvamento do doc {i+1} ('{nome_original_doc}'): {e_down}", exc_info=True)

            except PlaywrightTimeoutError: logging.warning("Seção 'Documentos do Custo' não encontrada ou timeout.")
            except Exception as e_docs: logging.error(f"Erro geral ao processar documentos geradores: {e_docs}", exc_info=True)

            # Volta para a lista principal após baixar tudo
            finally:
                logging.info("Tentando voltar para a lista de custos...")
                try:
                    page.locator("button:has-text('Voltar')").click()
                    expect(page.locator("h3:has-text('Solicitações de Custo')")).to_be_visible(timeout=30000)
                    page.wait_for_timeout(1000)
                    logging.info("Retornou para a lista de custos após downloads.")
                except Exception as e_voltar:
                     logging.error(f"Erro ao tentar voltar para a lista de custos: {e_voltar}")

            # Define o status final do robô com base nos downloads
            if not lista_arquivos_baixados_custa:
                 resultado_final["status_robo_final"] = f"Finalizado: Nenhum Arquivo Baixado (Status Portal: {status_portal_inicial})"
            else:
                 resultado_final["status_robo_final"] = "Finalizado com Sucesso"

        # --- AÇÃO: Confirmar Solicitação + Double Check ---
        elif any(s.lower() in status_portal_inicial.lower() for s in status_de_confirmacao):
            logging.info(f"Status '{status_portal_inicial}' requer confirmação. Iniciando fluxo de confirmação...")
            confirmacao_bem_sucedida = False
            try:
                botao_confirmar = linha_alvo.locator("button[bb-tooltip='Confirmar/Efetivar']")
                expect(botao_confirmar).to_be_visible(timeout=10000)
                botao_confirmar.click()
                logging.info("Botão 'Confirmar/Efetivar' clicado.")

                logging.info("Aguardando tela de despacho carregar...")
                page.locator("div.loader.is-loading").wait_for(state="hidden", timeout=45000)
                expect(page.locator("h3:has-text('DADOS DA SOLICITAÇÃO')")).to_be_visible(timeout=30000)
                logging.info("Página de despacho carregada.")

                page.locator("label.form-radio.form-inline span:has-text('Aprovar')").click()
                logging.info("Opção 'Aprovar' selecionada.")

                botao_salvar = page.locator("button:has-text('Salvar')")
                expect(botao_salvar).to_be_enabled(timeout=10000)
                botao_salvar.click()
                logging.info("Botão 'Salvar' clicado.")

                logging.info("Aguardando confirmação do salvamento e retorno para a lista...")
                page.locator("div.loader.is-loading").wait_for(state="hidden", timeout=60000)
                expect(page.locator("h3:has-text('Solicitações de Custo')")).to_be_visible(timeout=45000)
                logging.info("Confirmação realizada com sucesso. Retornou para a lista.")
                page.wait_for_timeout(2000) # Pausa maior após salvar para dar tempo de atualizar a lista

                confirmacao_bem_sucedida = True

            except Exception as e_confirm:
                 logging.error(f"Erro durante o fluxo de confirmação inicial para ID {solicitacao_id}: {e_confirm}", exc_info=True)
                 resultado_final["status_robo_final"] = "Erro: Falha na Confirmação (Portal)"
                 # Tenta voltar para a lista mesmo em caso de erro
                 try:
                      if page.locator("button:has-text('Voltar')").is_visible(timeout=2000):
                           page.locator("button:has-text('Voltar')").click()
                           logging.info("Tentou voltar para a lista após erro na confirmação.")
                 except: pass

            # --- Double Check após confirmação ---
            if confirmacao_bem_sucedida:
                logging.info("Iniciando double-check do status após confirmação...")
                novo_status_portal = None
                try:
                    # CORREÇÃO: Usa o botão Limpar para garantir reset completo
                    logging.info("Limpando formulário para double-check...")
                    try:
                        limpar_button_check = page.locator("button:has-text('Limpar')")
                        limpar_button_check.wait_for(state='visible', timeout=7000)
                        limpar_button_check.click()
                        page.wait_for_timeout(500)
                        logging.info("Formulário limpo via botão para double-check.")
                    except PlaywrightTimeoutError:
                         logging.warning("Botão 'Limpar' não encontrado para double-check. Tentando limpar campo NPJ diretamente.")
                         try:
                             input_npj_placeholder_check = page.locator("input[placeholder='Informe o NPJ']")
                             input_npj_placeholder_check.wait_for(state='visible', timeout=5000)
                             input_npj_placeholder_check.clear()
                             logging.info("Campo NPJ limpo diretamente para double-check.")
                         except Exception as e_clear_direct:
                              logging.error(f"Falha ao tentar limpar campo NPJ diretamente para double-check: {e_clear_direct}")
                              raise # Re-lança o erro se a limpeza direta falhar

                    # Preenche NPJ novamente
                    input_npj_check = page.locator("#npj")
                    expect(input_npj_check).to_be_visible(timeout=10000)
                    input_npj_check.fill(npj_para_buscar)
                    input_npj_check.press("Tab")
                    page.wait_for_timeout(500)
                    logging.info(f"NPJ {npj_para_buscar} preenchido novamente para double-check.")

                    # Aguarda a tabela recarregar
                    container_scroll_check = page.locator("div.tabs__pane.is-visible div[style*='overflow-y: auto']")
                    expect(container_scroll_check).to_be_visible(timeout=30000)
                    container_scroll_check.locator("tr[ng-repeat='item in $data']").first.wait_for(timeout=60000)

                    logging.info("Tabela recarregada para double-check. Procurando a solicitação novamente...")
                    page.wait_for_timeout(1500) # Pausa extra

                    linhas_check = container_scroll_check.locator("tr[ng-repeat='item in $data']").all()
                    linha_encontrada_check = False
                    for linha_check in linhas_check:
                        colunas_check = linha_check.locator("td").all()
                        if len(colunas_check) < 7: continue

                        num_sol_check = colunas_check[1].inner_text(timeout=2000).strip()
                        val_portal_check = colunas_check[6].inner_text(timeout=2000).strip()

                        if num_sol_check == num_solicitacao_bd and _comparar_valores(valor_bd, val_portal_check):
                            novo_status_portal = colunas_check[4].inner_text(timeout=2000).strip()
                            logging.info(f"Solicitação encontrada no double-check. Novo Status Portal: '{novo_status_portal}'")
                            linha_encontrada_check = True
                            break

                    if not linha_encontrada_check:
                        logging.error("Erro no double-check: Solicitação não encontrada na lista após confirmação.")
                        resultado_final["status_robo_final"] = "Erro: Falha Double-Check (Não encontrada)"
                    elif novo_status_portal is None:
                         logging.error("Erro no double-check: Não foi possível ler o novo status.")
                         resultado_final["status_robo_final"] = "Erro: Falha Double-Check (Leitura Status)"
                    else:
                        resultado_final["status_portal_encontrado"] = novo_status_portal
                        if any(s.lower() in novo_status_portal.lower() for s in status_de_confirmacao):
                            logging.error(f"Erro no double-check: Status do portal ainda é '{novo_status_portal}' após a confirmação.")
                            resultado_final["status_robo_final"] = "Erro: Falha na Confirmação (Status não mudou)"
                        else:
                            logging.info("Double-check OK: Status do portal foi atualizado após confirmação.")
                            resultado_final["status_robo_final"] = "Pendente"
                            resultado_final["usuario_confirmacao_id"] = _robot_user_id
                            logging.info(f"Status definido como 'Pendente'. Usuário de confirmação ID: {_robot_user_id}")

                except Exception as e_check:
                    logging.error(f"Erro durante o double-check: {e_check}", exc_info=True)
                    resultado_final["status_robo_final"] = "Erro: Falha Double-Check (Exceção)"

        # --- AÇÃO: Nenhuma (Apenas Monitoramento) ---
        else:
            logging.info(f"Status do portal é '{status_portal_inicial}'. Nenhuma ação automática (download/confirmação) definida.")
            resultado_final["status_robo_final"] = "Pendente"
            logging.info(f"Status da solicitação no OneCost será mantido/definido como 'Pendente'. Status portal '{status_portal_inicial}' foi registrado.")

        resultado_final["lista_arquivos_baixados"] = lista_arquivos_baixados_custa

    # --- Tratamento de Erros Gerais ---
    except PlaywrightTimeoutError as e:
        logging.error(f"Timeout durante processamento da ID {solicitacao_id}: {e}", exc_info=False)
        resultado_final["status_robo_final"] = f"Erro: Timeout Playwright ({e.__class__.__name__})"
        try:
             npj_dir_erro = _limpar_nome_arquivo(npj_para_buscar if npj_para_buscar else "ERRO_SEM_NPJ")
             ts = int(time.time()) # Timestamp para nome único
             screenshot_path_completo = COMPROVANTES_DIR / npj_dir_erro / f"erro_timeout_{solicitacao_id}_{ts}.png"
             screenshot_path_completo.parent.mkdir(parents=True, exist_ok=True)
             page.screenshot(path=str(screenshot_path_completo), timeout=10000)
             logging.info(f"Screenshot de erro salvo em: {screenshot_path_completo}")
             screenshot_relativo = screenshot_path_completo.relative_to(COMPROVANTES_DIR)
             resultado_final["lista_arquivos_baixados"].append(screenshot_relativo.as_posix())
        except Exception as e_screen: logging.error(f"Falha ao salvar screenshot de erro: {e_screen}")

    except Exception as e:
        logging.exception(f"Erro crítico inesperado durante processamento da ID {solicitacao_id}")
        resultado_final["status_robo_final"] = f"Erro Crítico Inesperado: {type(e).__name__}"
        try:
             npj_dir_erro = _limpar_nome_arquivo(npj_para_buscar if npj_para_buscar else "ERRO_SEM_NPJ")
             ts = int(time.time()) # Timestamp
             screenshot_path_completo = COMPROVANTES_DIR / npj_dir_erro / f"erro_critico_{solicitacao_id}_{ts}.png"
             screenshot_path_completo.parent.mkdir(parents=True, exist_ok=True)
             page.screenshot(path=str(screenshot_path_completo), timeout=10000)
             logging.info(f"Screenshot de erro crítico salvo em: {screenshot_path_completo}")
             screenshot_relativo = screenshot_path_completo.relative_to(COMPROVANTES_DIR)
             resultado_final["lista_arquivos_baixados"].append(screenshot_relativo.as_posix())
        except Exception as e_screen: logging.error(f"Falha ao salvar screenshot de erro crítico: {e_screen}")

    # Log final do processamento desta solicitação
    logging.info(f"Processamento finalizado para ID {solicitacao_id}. Status Robô final: '{resultado_final['status_robo_final']}'. Status Portal (final): '{resultado_final['status_portal_encontrado']}'. Arquivos: {len(resultado_final['lista_arquivos_baixados'])}.")

    return resultado_final

