import logging
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.utils.conv import escape_filter_chars

from config import AD_BASE_DN, AD_DOMAIN, AD_SERVER_IP, AD_SERVICE_PASS, AD_SERVICE_USER

logger = logging.getLogger(__name__)


def extrair_setor_bb_do_dn(dn: str):
    for parte in str(dn or "").split(","):
        if parte.startswith("OU=BB_"):
            return parte.replace("OU=", "")
    return None


def autenticar_e_obter_setor(usuario: str, senha: str):
    """
    Reaproveita a mesma ideia do OneLog:
    autentica no AD e identifica a primeira OU que começa com 'BB_'.
    """
    if not AD_SERVER_IP or not AD_DOMAIN or not AD_BASE_DN:
        logger.warning("Configuracao AD incompleta. Login AD indisponivel para '%s'.", usuario)
        return {"status": "erro", "mensagem": "Login AD indisponivel no momento."}

    server = Server(
        AD_SERVER_IP,
        port=636,
        use_ssl=True,
        get_info=ALL,
        connect_timeout=5,
    )
    user_principal = f"{usuario}@{AD_DOMAIN}"

    try:
        conn = Connection(
            server,
            user=user_principal,
            password=senha,
            auto_bind=True,
            receive_timeout=10,
        )
        logger.info("Autenticacao AD bem-sucedida para '%s'.", usuario)

        conn.search(
            search_base=AD_BASE_DN,
            search_filter=f"(sAMAccountName={usuario})",
            search_scope=SUBTREE,
            attributes=["distinguishedName"],
        )

        if not conn.entries:
            return {"status": "erro", "mensagem": "Dados do usuario nao encontrados no diretorio."}

        dn = str(conn.entries[0].distinguishedName)
        setor = extrair_setor_bb_do_dn(dn)
        if setor:
            return {"status": "sucesso", "setor": setor}

        logger.warning("Usuario '%s' autenticou no AD, mas sem OU BB_.", usuario)
        return {"status": "erro", "mensagem": "Acesso negado: usuario sem setor BB_ vinculado no AD."}
    except Exception as exc:
        logger.error("Falha de login AD para '%s': %s", usuario, exc)
        error_text = str(exc).lower()
        if "timed out" in error_text or "socket" in error_text or "connection" in error_text:
            return {"status": "erro", "mensagem": "Nao foi possivel conectar ao Active Directory no momento."}
        return {"status": "erro", "mensagem": "Usuario ou senha do Windows incorretos."}


def listar_ous_bb_ad():
    """
    Lista globalmente as OUs do AD que representam setores BB_.
    Usa conta de servico dedicada ou, se ausente, faz fallback para as variaveis do OneLog.
    """
    if not AD_SERVICE_USER or not AD_SERVICE_PASS:
        logger.warning("Credenciais de servico do AD nao configuradas. Listagem global de setores indisponivel.")
        return []

    if not AD_SERVER_IP or not AD_DOMAIN or not AD_BASE_DN:
        logger.warning("Configuracao AD incompleta. Nao foi possivel listar setores.")
        return []

    server = Server(
        AD_SERVER_IP,
        port=636,
        use_ssl=True,
        get_info=ALL,
        connect_timeout=5,
    )
    try:
        conn = Connection(
            server,
            user=f"{AD_SERVICE_USER}@{AD_DOMAIN}",
            password=AD_SERVICE_PASS,
            auto_bind=True,
            receive_timeout=10,
        )
        conn.search(
            search_base=AD_BASE_DN,
            search_filter="(objectCategory=organizationalUnit)",
            search_scope=SUBTREE,
            attributes=["name"],
        )

        setores = sorted({
            str(entry.name)
            for entry in conn.entries
            if str(entry.name).startswith("BB_")
        })
        return setores
    except Exception as exc:
        logger.error("Falha ao listar setores do AD: %s", exc)
        return []


def mapear_setores_bb_por_usuarios(usernames):
    """
    Consulta o AD com conta de serviço e retorna o setor BB_ encontrado para cada
    username informado. Mantém resultado por usuário para permitir backfill em lote.
    """
    usernames_normalizados = [str(username or "").strip() for username in usernames if str(username or "").strip()]
    resultados = {}

    if not usernames_normalizados:
        return resultados

    if not AD_SERVICE_USER or not AD_SERVICE_PASS:
        raise RuntimeError("Credenciais de servico do AD nao configuradas para o backfill.")

    if not AD_SERVER_IP or not AD_DOMAIN or not AD_BASE_DN:
        raise RuntimeError("Configuracao do AD incompleta. Backfill indisponivel.")

    server = Server(
        AD_SERVER_IP,
        port=636,
        use_ssl=True,
        get_info=ALL,
        connect_timeout=5,
    )

    try:
        conn = Connection(
            server,
            user=f"{AD_SERVICE_USER}@{AD_DOMAIN}",
            password=AD_SERVICE_PASS,
            auto_bind=True,
            receive_timeout=10,
        )
    except Exception as exc:
        logger.error("Falha ao autenticar conta de servico no AD para backfill: %s", exc)
        raise RuntimeError("Nao foi possivel autenticar a conta de servico no Active Directory.") from exc

    for username in usernames_normalizados:
        try:
            filtro_usuario = escape_filter_chars(username)
            conn.search(
                search_base=AD_BASE_DN,
                search_filter=f"(&(objectClass=user)(sAMAccountName={filtro_usuario}))",
                search_scope=SUBTREE,
                attributes=["distinguishedName"],
            )

            if not conn.entries:
                resultados[username] = {
                    "status": "nao_encontrado",
                    "mensagem": "Usuario nao localizado no AD.",
                }
                continue

            dn = str(conn.entries[0].distinguishedName)
            setor = extrair_setor_bb_do_dn(dn)
            if setor:
                resultados[username] = {
                    "status": "sucesso",
                    "setor": setor,
                    "distinguished_name": dn,
                }
            else:
                resultados[username] = {
                    "status": "sem_setor_bb",
                    "mensagem": "Usuario encontrado no AD, mas sem OU BB_.",
                    "distinguished_name": dn,
                }
        except Exception as exc:
            logger.error("Falha ao buscar setor no AD para '%s': %s", username, exc)
            resultados[username] = {
                "status": "erro",
                "mensagem": f"Erro ao consultar AD: {exc}",
            }

    return resultados
