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
# Importar o ID do usuário robô (preenchido após o login)
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
        # Remove R$, espaços, troca . por nada e , por .
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

    # Compara com uma pequena tolerância para evitar problemas de arredondamento float vs Decimal
    comparacao = abs(valor_bd - valor_portal_decimal) < Decimal('0.001')
    logging.debug(f"Comparando Valor BD ({valor_bd}) com Valor Portal ({valor_portal_decimal}): {'Iguais' if comparacao else 'Diferentes'}")
    return comparacao
# --- Fim Funções Auxiliares ---


# --- Função Principal ---
def processar_solicitacao_especifica(page: Page, solicitacao_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processa uma solicitação de custa específica:
    1. Localiza a custa pelo NPJ, Nº Solicitação e Valor.
    2. CAPTURA ESPECIFICAÇÃO da lista.
    3. SEMPRE entra em Detalhes.
    4. CAPTURA NÚMERO DO PROCESSO (CNJ) da tela de detalhes.
    5. Baixa comprovantes/documentos se status for de conclusão.
    6. Confirma a solicitação se status for 'Aguardando Confirmação' e REVERIFICA o status.
    7. Retorna dados atualizados para a API (status, arquivos, ID de confirmação, especificacao, numero_processo).
    """
    npj_para_buscar = solicitacao_info.get("npj")
    solicitacao_id = solicitacao_info.get("id")
    num_solicitacao_bd = solicitacao_info.get("numero_solicitacao")
    # Guarda o número do processo que veio do BD (pode ser None)
    numero_processo_bd = solicitacao_info.get("numero_processo")

    try:
        valor_bd = Decimal(str(solicitacao_info.get("valor", "0.0")))
    except InvalidOperation:
        logging.error(f"Valor inválido na solicitação ID {solicitacao_id}: {solicitacao_info.get('valor')}. Usando 0.0.")
        valor_bd = Decimal("0.0")

    # Estrutura do resultado a ser retornado para a API
    resultado_final = {
        "solicitacao_id": solicitacao_id,
        "numero_processo": numero_processo_bd, # Inicia com o valor do BD, será atualizado se encontrado
        "especificacao": None, # Campo para a especificação
        "comprovantes_path": [], # Lista de caminhos relativos (NOME CORRETO PARA A API)
        "status_portal": None, # Status lido do portal (o último lido)
        "status_robo": "Erro: Falha não especificada", # Status final para o OneCost (NOME CORRETO)
        "usuario_confirmacao_id": None, # ID do robô se ele confirmar
        "dados_custas_encontrados_debug": {} # Dados lidos da linha da tabela (mantido para logs/debug)
    }

    logging.info(f"Iniciando processamento para Solicitação ID: {solicitacao_id}, NPJ: {npj_para_buscar}")

    if not npj_para_buscar:
        logging.error(f"NPJ não fornecido para busca na solicitação ID {solicitacao_id}.")
        resultado_final["status_robo"] = "Erro: NPJ não fornecido"
        return resultado_final

    linha_alvo = None
    especificacao_capturada = None # Variável para guardar a especificação da lista
    status_portal_inicial = None # Variável para guardar o status da lista
    valor_portal_texto_capturado = None # Variável para guardar o valor da lista

    # --- CORREÇÃO DO BUG (UnboundLocalError) ---
    # Inicializa a variável aqui para garantir que ela exista no 'finally'
    voltar_para_lista_necessario = False
    # ------------------------------------------

    try:
        # 1. Garantir que está na página certa e Limpar Busca
        logging.info("Verificando página de consulta e limpando busca anterior...")
        try:
            page.wait_for_selector("input#npj, button:has-text('Limpar')", timeout=20000)
            logging.info("Página de consulta de custos confirmada.")
            limpar_button = page.locator("button:has-text('Limpar')")
            limpar_button.wait_for(state='visible', timeout=7000)
            limpar_button.click()
            page.wait_for_timeout(500) # Pequena pausa após limpar
            logging.info("Formulário limpo.")
        except PlaywrightTimeoutError:
            logging.warning("Botão 'Limpar' não encontrado ou página incorreta. Tentando continuar...")
            try:
                # Tenta limpar campo NPJ diretamente
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
            container_scroll = page.locator("div.tabs__pane.is-visible div[style*='overflow-y: auto']")
            expect(container_scroll).to_be_visible(timeout=30000)
            # Espera pela primeira linha de dados na tabela
            container_scroll.locator("tr[ng-repeat='item in $data']").first.wait_for(timeout=60000)
            logging.info("Tabela de resultados carregada.")
            page.wait_for_timeout(1500) # Pausa extra para garantir renderização
        except PlaywrightTimeoutError:
            logging.warning(f"Tabela de custos não apareceu após preencher o NPJ {npj_para_buscar}.")
            resultado_final["status_robo"] = "Erro: Tabela de custos não encontrada"
            return resultado_final

        # 3. Encontrar a Custa Específica na Tabela e CAPTURAR DADOS INICIAIS
        logging.info(f"Procurando custa com Nº Solicitação '{num_solicitacao_bd}' e Valor próximo a '{valor_bd}'...")
        todas_as_linhas = container_scroll.locator("tr[ng-repeat='item in $data']").all()

        if not todas_as_linhas:
            logging.warning(f"Nenhuma linha encontrada na tabela para o NPJ {npj_para_buscar}.")
            resultado_final["status_robo"] = "Erro: Nenhuma custa na tabela"
            return resultado_final

        for linha in todas_as_linhas:
            try:
                colunas = linha.locator("td").all()
                if len(colunas) < 7: continue # Pula linhas incompletas

                num_solicitacao_portal = colunas[1].inner_text(timeout=2000).strip()
                valor_portal_texto = colunas[6].inner_text(timeout=2000).strip()

                logging.debug(f"Linha lida: Nº Sol: {num_solicitacao_portal}, Valor: {valor_portal_texto}")

                # Compara número da solicitação e valor (com tolerância)
                if num_solicitacao_portal == num_solicitacao_bd and _comparar_valores(valor_bd, valor_portal_texto):
                    # Captura os dados ANTES de clicar em detalhes
                    status_portal_inicial = colunas[4].inner_text(timeout=2000).strip()
                    especificacao_capturada = colunas[3].inner_text(timeout=2000).strip() # Captura a especificação aqui
                    valor_portal_texto_capturado = valor_portal_texto # Guarda o valor exato lido

                    logging.info(f"Custa correspondente (ID {solicitacao_id}) encontrada! Status Lista: '{status_portal_inicial}', Especificação: '{especificacao_capturada}'")
                    linha_alvo = linha

                    # Atualiza resultado_final com dados da lista
                    resultado_final["status_portal"] = status_portal_inicial
                    resultado_final["especificacao"] = especificacao_capturada
                    # Mantém dados_custas_encontrados para logs/debug se útil
                    resultado_final["dados_custas_encontrados_debug"] = {
                         "numero_solicitacao": num_solicitacao_portal,
                         "valor": valor_portal_texto_capturado,
                         "status": status_portal_inicial,
                         "especificacao": especificacao_capturada
                    }
                    break # Encontrou a linha, sai do loop

            except Exception as e_linha:
                logging.error(f"Erro ao processar linha da tabela: {e_linha}", exc_info=True)
                continue # Tenta a próxima linha

        if not linha_alvo:
            logging.warning(f"Nenhuma custa correspondente a Nº Sol '{num_solicitacao_bd}' e Valor '{valor_bd}' encontrada para NPJ {npj_para_buscar}.")
            resultado_final["status_robo"] = "Erro: Custa específica não encontrada"
            return resultado_final

        # 4. SEMPRE CLICAR EM DETALHES para buscar o Número do Processo (CNJ)
        numero_processo_completo_detalhes = None # Variável local para o número pego nos detalhes
        voltar_para_lista_necessario = True # Flag para saber se precisa voltar (assume que sim)
        try:
            logging.info(f"Entrando em 'Detalhes' para buscar Número do Processo (CNJ) para ID {solicitacao_id}...")
            botao_detalhes = linha_alvo.locator("button[bb-tooltip='Detalhes']")
            expect(botao_detalhes).to_be_visible(timeout=10000)
            botao_detalhes.click()
            logging.info("Botão 'Detalhes' clicado.")

            # Aguarda página de detalhes carregar
            logging.info("Aguardando página de detalhes...")
            # Usa um seletor mais genérico que deve aparecer na tela de detalhes
            expect(page.locator("h3:has-text('Detalhar Custo')")).to_be_visible(timeout=45000)
            # Espera um pouco mais para garantir que os 'chips' carreguem
            page.wait_for_timeout(2000)
            logging.info("Página de detalhes carregada.")

            # Tenta extrair número completo do processo (CNJ)
            try:
                 processo_chip_desc = page.locator('div[bb-title="Processo"] span.chip__desc').first
                 processo_chip_desc.wait_for(state='visible', timeout=10000) # Timeout um pouco maior aqui
                 numero_processo_completo_detalhes = processo_chip_desc.inner_text().strip()
                 if numero_processo_completo_detalhes:
                      logging.info(f"Número do Processo (CNJ) completo extraído: {numero_processo_completo_detalhes}")
                      # Atualiza o resultado final APENAS SE o BD estiver vazio OU for diferente
                      if not resultado_final["numero_processo"] or resultado_final["numero_processo"] != numero_processo_completo_detalhes:
                           logging.info(f"Atualizando número do processo no resultado para: {numero_processo_completo_detalhes}")
                           resultado_final["numero_processo"] = numero_processo_completo_detalhes
                 else:
                      logging.warning("Elemento do número do processo (CNJ) encontrado, mas estava vazio.")
            except PlaywrightTimeoutError:
                 logging.warning("Não foi possível encontrar/ler o elemento do número do processo (CNJ) completo na tela de detalhes.")
            except Exception as e:
                 logging.error(f"Erro ao extrair número do processo (CNJ) completo: {e}")

        except Exception as e_detalhes:
            logging.error(f"Erro ao tentar acessar ou processar a página de 'Detalhes' para ID {solicitacao_id}: {e_detalhes}", exc_info=True)
            # Se deu erro ao entrar nos detalhes, não adianta tentar baixar/confirmar, mas registra o status da lista
            resultado_final["status_robo"] = "Erro: Falha ao acessar Detalhes"
            # Não precisa voltar para a lista se não conseguiu nem entrar
            voltar_para_lista_necessario = False

        # 5. Processar a Ação (Download/Confirmação/Nada) com base no Status da Lista
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

        # --- AÇÃO: Baixar Comprovantes (Só se status for de conclusão E conseguiu entrar nos detalhes) ---
        if any(s.lower() in status_portal_inicial.lower() for s in status_de_conclusao) and voltar_para_lista_necessario:
            logging.info(f"Status '{status_portal_inicial}' indica conclusão. Iniciando download de documentos...")

            # Cria diretório para os arquivos (baseado no NPJ) - Lógica mantida
            npj_limpo = _limpar_nome_arquivo(npj_para_buscar)
            diretorio_npj = COMPROVANTES_DIR / npj_limpo
            diretorio_npj.mkdir(parents=True, exist_ok=True)
            logging.info(f"Diretório para arquivos: {diretorio_npj}")

            # Define partes do nome do arquivo (Usa o número do processo pego dos detalhes se disponível)
            num_proc_para_nome = _limpar_nome_arquivo(resultado_final["numero_processo"] or npj_para_buscar)
            valor_custo_str = resultado_final["dados_custas_encontrados_debug"].get('valor', '0') # Usa valor da lista
            espec_custo = resultado_final["especificacao"] or 'Desconhecida' # Usa especificação da lista

            # --- Baixar Comprovante(s) PDF --- (Já está na página de detalhes)
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


            # --- Baixar Documentos Geradores --- (Já está na página de detalhes)
            logging.info("Procurando seção 'Documentos do Custo'...")
            try:
                documentos_section = page.locator("div.accordion__item[bb-item-title='Documentos do Custo']")
                documentos_section.wait_for(state='visible', timeout=10000)
                if 'is-open' not in (documentos_section.get_attribute('class', timeout=1000) or ''):
                    logging.info("Abrindo seção 'Documentos do Custo'...")
                    documentos_section.locator(".accordion__title").click()
                    # Espera a tabela ou um indicativo de que não há documentos
                    try:
                        documentos_section.locator("table").wait_for(state='visible', timeout=10000)
                    except PlaywrightTimeoutError:
                        # Verifica se existe mensagem de "Nenhum documento" (ajustar seletor se necessário)
                        if documentos_section.locator("text=/Nenhum documento encontrado/i").is_visible(timeout=1000):
                            logging.info("Nenhum documento gerador encontrado nesta seção (mensagem explícita).")
                        else:
                            logging.warning("Tabela de documentos não encontrada e sem mensagem de 'nenhum documento'.")

                links_download_docs = documentos_section.locator("td a[href*='/paj/resources/app/v0/processo/documento/download/']").all()

                if not links_download_docs:
                    # Log movido para dentro do bloco try/except acima
                    pass # logging.info("Nenhum documento gerador encontrado nesta seção.")
                else:
                    logging.info(f"Encontrados {len(links_download_docs)} documento(s) gerador(es) para baixar.")
                    for i, link_doc in enumerate(links_download_docs):
                        nome_original_doc = f"DocumentoGerador_{i+1}"
                        try:
                            # Tenta pegar nome do span na mesma linha
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
                            ext = Path(suggested_filename).suffix or ".pdf" # Garante uma extensão
                            nome_original_doc_sem_ext = Path(nome_original_doc).stem
                            # Monta nome do arquivo final
                            nome_arquivo_doc = f"{_limpar_nome_arquivo(nome_original_doc_sem_ext)}_{num_proc_para_nome}_{_limpar_nome_arquivo(num_solicitacao_bd)}_{_limpar_nome_arquivo(valor_custo_str)}{ext}"
                            caminho_arquivo_doc_completo = diretorio_npj / nome_arquivo_doc

                            download.save_as(caminho_arquivo_doc_completo)

                            caminho_relativo_doc = caminho_arquivo_doc_completo.relative_to(COMPROVANTES_DIR)
                            lista_arquivos_baixados_custa.append(caminho_relativo_doc.as_posix())

                            logging.info(f"Download doc {i+1} ('{suggested_filename}') concluído. Caminho relativo: {caminho_relativo_doc.as_posix()}")
                            time.sleep(1) # Pequena pausa entre downloads

                        except PlaywrightTimeoutError as e_down_timeout: logging.error(f"Timeout ao esperar download do doc {i+1} ('{nome_original_doc}'): {e_down_timeout}")
                        except Exception as e_down: logging.error(f"Erro durante download ou salvamento do doc {i+1} ('{nome_original_doc}'): {e_down}", exc_info=True)

            except PlaywrightTimeoutError: logging.warning("Seção 'Documentos do Custo' não encontrada ou timeout.")
            except Exception as e_docs: logging.error(f"Erro geral ao processar documentos geradores: {e_docs}", exc_info=True)


            # Define o status final do robô com base nos downloads
            if not lista_arquivos_baixados_custa:
                 resultado_final["status_robo"] = f"Finalizado: Nenhum Arquivo Baixado (Status Portal: {status_portal_inicial})"
            else:
                 resultado_final["status_robo"] = "Finalizado com Sucesso"

            # <<< IMPORTANTE >>> O 'Voltar' agora será tratado no 'finally' geral

        # --- AÇÃO: Confirmar Solicitação + Double Check (Só se status for de confirmação E NÃO deu erro ao entrar nos detalhes) ---
        elif any(s.lower() in status_portal_inicial.lower() for s in status_de_confirmacao) and voltar_para_lista_necessario:

            # Voltar para a lista ANTES de clicar em confirmar
            logging.info("Status requer confirmação. Voltando para a lista antes de confirmar...")
            try:
                page.locator("button:has-text('Voltar')").click()
                expect(page.locator("h3:has-text('Solicitações de Custo')")).to_be_visible(timeout=30000)
                page.wait_for_timeout(1500) # Pausa maior para garantir que a lista recarregue
                logging.info("Retornou para a lista de custos. Procurando a linha novamente para confirmar...")
                voltar_para_lista_necessario = False # Já voltamos, não precisa voltar de novo no finally

                # Reencontrar a linha na lista atualizada
                container_scroll_confirm = page.locator("div.tabs__pane.is-visible div[style*='overflow-y: auto']")
                expect(container_scroll_confirm).to_be_visible(timeout=30000)
                # Espera a primeira linha carregar após a atualização
                container_scroll_confirm.locator("tr[ng-repeat='item in $data']").first.wait_for(timeout=60000)
                linhas_confirm = container_scroll_confirm.locator("tr[ng-repeat='item in $data']").all()
                linha_alvo_confirm = None
                for linha_c in linhas_confirm:
                     colunas_c = linha_c.locator("td").all()
                     if len(colunas_c) < 7: continue
                     num_sol_c = colunas_c[1].inner_text(timeout=2000).strip()
                     val_portal_c = colunas_c[6].inner_text(timeout=2000).strip()
                     if num_sol_c == num_solicitacao_bd and _comparar_valores(valor_bd, val_portal_c):
                         linha_alvo_confirm = linha_c
                         logging.info("Linha reencontrada para confirmação.")
                         break

                if not linha_alvo_confirm:
                     raise Exception("Não foi possível reencontrar a linha na lista após voltar dos detalhes.")

                # Agora sim, inicia o fluxo de confirmação usando linha_alvo_confirm
                logging.info(f"Iniciando fluxo de confirmação para ID {solicitacao_id}...")
                confirmacao_bem_sucedida = False
                try:
                    botao_confirmar = linha_alvo_confirm.locator("button[bb-tooltip='Confirmar/Efetivar']")
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
                    # Espera voltar para a H3 principal da lista
                    expect(page.locator("h3:has-text('Solicitações de Custo')")).to_be_visible(timeout=45000)
                    logging.info("Confirmação realizada com sucesso. Retornou para a lista.")
                    page.wait_for_timeout(2000) # Pausa maior após salvar para dar tempo de atualizar a lista

                    confirmacao_bem_sucedida = True

                except Exception as e_confirm:
                    logging.error(f"Erro durante o fluxo de confirmação para ID {solicitacao_id}: {e_confirm}", exc_info=True)
                    resultado_final["status_robo"] = "Erro: Falha na Confirmação (Portal)"
                    # Tenta voltar para a lista mesmo em caso de erro, se ainda estiver na tela de despacho
                    try:
                        if page.locator("h3:has-text('DADOS DA SOLICITAÇÃO')").is_visible(timeout=2000):
                             page.locator("button:has-text('Voltar')").click()
                             logging.info("Tentou voltar para a lista após erro na confirmação.")
                             voltar_para_lista_necessario = False # Já voltamos (ou tentamos)
                    except: pass


                # --- Double Check após confirmação ---
                if confirmacao_bem_sucedida:
                    logging.info("Iniciando double-check do status após confirmação...")
                    novo_status_portal = None
                    try:
                        # Limpa busca para garantir refresh
                        logging.info("Limpando formulário para double-check...")
                        try:
                            limpar_button_check = page.locator("button:has-text('Limpar')")
                            limpar_button_check.wait_for(state='visible', timeout=7000)
                            limpar_button_check.click()
                            page.wait_for_timeout(500)
                            logging.info("Formulário limpo via botão para double-check.")
                        except PlaywrightTimeoutError:
                             logging.warning("Botão 'Limpar' não encontrado para double-check. Tentando limpar campo NPJ.")
                             try:
                                 input_npj_placeholder_check = page.locator("input[placeholder='Informe o NPJ']")
                                 input_npj_placeholder_check.wait_for(state='visible', timeout=5000)
                                 input_npj_placeholder_check.clear()
                                 logging.info("Campo NPJ limpo diretamente para double-check.")
                             except Exception as e_clear_direct:
                                   logging.error(f"Falha ao tentar limpar campo NPJ para double-check: {e_clear_direct}")
                                   raise # Re-lança o erro

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
                        logging.info("Tabela recarregada para double-check. Procurando a solicitação...")
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
                                # Atualiza a especificação no resultado final também no double check
                                especificacao_check = colunas_check[3].inner_text(timeout=2000).strip()
                                resultado_final["especificacao"] = especificacao_check
                                resultado_final["status_portal"] = novo_status_portal # Atualiza status final
                                break

                        if not linha_encontrada_check:
                            logging.error("Erro no double-check: Solicitação não encontrada na lista após confirmação.")
                            resultado_final["status_robo"] = "Erro: Falha Double-Check (Não encontrada)"
                        elif novo_status_portal is None:
                             logging.error("Erro no double-check: Não foi possível ler o novo status.")
                             resultado_final["status_robo"] = "Erro: Falha Double-Check (Leitura Status)"
                        else:
                            # Compara novo status com os de confirmação
                            if any(s.lower() in novo_status_portal.lower() for s in status_de_confirmacao):
                                logging.error(f"Erro no double-check: Status do portal ainda é '{novo_status_portal}' após a confirmação.")
                                resultado_final["status_robo"] = "Erro: Falha na Confirmação (Status não mudou)"
                            else:
                                logging.info("Double-check OK: Status do portal foi atualizado após confirmação.")
                                resultado_final["status_robo"] = "Pendente" # Volta para pendente após confirmar
                                resultado_final["usuario_confirmacao_id"] = _robot_user_id
                                logging.info(f"Status definido como 'Pendente'. Usuário de confirmação ID: {_robot_user_id}")

                    except Exception as e_check:
                        logging.error(f"Erro durante o double-check: {e_check}", exc_info=True)
                        resultado_final["status_robo"] = "Erro: Falha Double-Check (Exceção)"

            except Exception as e_voltar_lista:
                 logging.error(f"Erro ao tentar voltar para a lista antes de confirmar: {e_voltar_lista}", exc_info=True)
                 resultado_final["status_robo"] = "Erro: Falha ao voltar para lista (Confirmação)"
                 voltar_para_lista_necessario = False # Não precisa voltar no final


        # --- AÇÃO: Nenhuma Ação Específica (Apenas Monitoramento e Captura de Dados) ---
        elif voltar_para_lista_necessario: # Só executa se conseguiu entrar nos detalhes
            logging.info(f"Status do portal é '{status_portal_inicial}'. Nenhuma ação automática (download/confirmação) definida.")
            # Mantém status Pendente a menos que já esteja finalizado no OneCost ou seja erro
            if not solicitacao_info.get("usuario_finalizacao_id") and "Erro" not in (solicitacao_info.get("status_robo") or ""):
                 resultado_final["status_robo"] = "Pendente"
                 logging.info(f"Status da solicitação no OneCost será mantido/definido como 'Pendente'. Dados capturados (Especificação, Nº Processo) serão enviados.")
            else:
                 resultado_final["status_robo"] = solicitacao_info.get("status_robo") # Mantém o status que já estava
                 logging.info(f"Solicitação já finalizada ou em erro no OneCost. Mantendo status '{resultado_final['status_robo']}'. Dados capturados (Especificação, Nº Processo) serão enviados se atualizados.")

            # <<< IMPORTANTE >>> O 'Voltar' agora será tratado no 'finally' geral

        # Atribui a lista de arquivos baixados (pode estar vazia)
        resultado_final["comprovantes_path"] = lista_arquivos_baixados_custa

    # --- Tratamento de Erros Gerais ---
    except PlaywrightTimeoutError as e:
        logging.error(f"Timeout durante processamento da ID {solicitacao_id}: {e}", exc_info=False) # Não loga stacktrace completo para timeout
        resultado_final["status_robo"] = f"Erro: Timeout Playwright ({e.__class__.__name__})"
        # Tenta salvar screenshot
        try:
             npj_dir_erro = _limpar_nome_arquivo(npj_para_buscar if npj_para_buscar else f"ERRO_ID_{solicitacao_id}")
             ts = int(time.time()) # Timestamp para nome único
             screenshot_path_completo = COMPROVANTES_DIR / npj_dir_erro / f"erro_timeout_{solicitacao_id}_{ts}.png"
             screenshot_path_completo.parent.mkdir(parents=True, exist_ok=True) # Garante que diretório exista
             page.screenshot(path=str(screenshot_path_completo), timeout=10000)
             logging.info(f"Screenshot de erro salvo em: {screenshot_path_completo}")
             screenshot_relativo = screenshot_path_completo.relative_to(COMPROVANTES_DIR)
             # Anexa APENAS o screenshot ao resultado se houver erro
             resultado_final["comprovantes_path"] = [screenshot_relativo.as_posix()]
        except Exception as e_screen: logging.error(f"Falha ao salvar screenshot de erro de timeout: {e_screen}")
        voltar_para_lista_necessario = False # Timeout, provavelmente não está na tela certa para voltar

    except Exception as e:
        logging.exception(f"Erro crítico inesperado durante processamento da ID {solicitacao_id}") # Loga stacktrace completo
        resultado_final["status_robo"] = f"Erro Crítico Inesperado: {type(e).__name__}"
        # Tenta salvar screenshot
        try:
             npj_dir_erro = _limpar_nome_arquivo(npj_para_buscar if npj_para_buscar else f"ERRO_ID_{solicitacao_id}")
             ts = int(time.time()) # Timestamp
             screenshot_path_completo = COMPROVANTES_DIR / npj_dir_erro / f"erro_critico_{solicitacao_id}_{ts}.png"
             screenshot_path_completo.parent.mkdir(parents=True, exist_ok=True)
             page.screenshot(path=str(screenshot_path_completo), timeout=10000)
             logging.info(f"Screenshot de erro crítico salvo em: {screenshot_path_completo}")
             screenshot_relativo = screenshot_path_completo.relative_to(COMPROVANTES_DIR)
             resultado_final["comprovantes_path"] = [screenshot_relativo.as_posix()]
        except Exception as e_screen: logging.error(f"Falha ao salvar screenshot de erro crítico: {e_screen}")
        # Tenta verificar se precisa voltar, mas pode falhar
        try:
             if page.locator("h3:has-text('Detalhar Custo')").is_visible(timeout=1000):
                  pass # Precisa voltar
             else:
                   voltar_para_lista_necessario = False
        except:
             voltar_para_lista_necessario = False


    finally:
        # --- <<< NOVO >>> Bloco Finally para garantir que volte para a lista ---
        if voltar_para_lista_necessario:
            logging.info("Bloco Finally: Verificando se é necessário voltar para a lista de custos...")
            try:
                # Verifica se ainda está na tela de detalhes antes de tentar voltar
                if page.locator("h3:has-text('Detalhar Custo')").is_visible(timeout=3000):
                    page.locator("button:has-text('Voltar')").click()
                    expect(page.locator("h3:has-text('Solicitações de Custo')")).to_be_visible(timeout=30000)
                    page.wait_for_timeout(1000)
                    logging.info("Bloco Finally: Retornou para a lista de custos.")
                else:
                    logging.info("Bloco Finally: Já estava na lista de custos ou em outra tela, não voltou.")
            except Exception as e_voltar_finally:
                 logging.error(f"Bloco Finally: Erro ao tentar voltar para a lista de custos: {e_voltar_finally}")
                 # Não fazer nada drástico aqui, apenas logar.

    # --- CORREÇÃO (custos_manager.py) ---
    # Usa 'status_robo' ao invés de 'status_robo_final' no log
    logging.info(f"Processamento finalizado para ID {solicitacao_id}. Status Robô final: '{resultado_final['status_robo']}'. Status Portal (final): '{resultado_final['status_portal']}'. Especificação: '{resultado_final['especificacao']}'. Nº Processo: '{resultado_final['numero_processo']}'. Arquivos: {len(resultado_final['comprovantes_path'])}.")
    # ------------------------------------

    return resultado_final