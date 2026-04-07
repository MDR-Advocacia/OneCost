#!/usr/bin/env python3
import argparse
import os
import sys
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy import func


APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from bd.database import SessionLocal, engine  # noqa: E402
from bd.models import SolicitacaoCusta, User  # noqa: E402


ARCHIVE_REASON_TEMPLATE = "Duplicata consolidada no ID {canonical_id}"
UNIQUE_INDEX_NAME = "ux_solicitacoes_custas_npj_numero_active"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Consolida solicitações duplicadas por NPJ + número da solicitação."
    )
    parser.add_argument("--apply", action="store_true", help="Aplica as mudanças no banco.")
    parser.add_argument("--limit", type=int, default=None, help="Limita a quantidade de grupos processados.")
    parser.add_argument("--npj", help="Processa somente um NPJ específico.")
    parser.add_argument("--numero-solicitacao", dest="numero_solicitacao", help="Filtra por número da solicitação.")
    parser.add_argument(
        "--include-archived-only",
        action="store_true",
        help="Inclui também grupos onde todas as duplicatas já estão arquivadas."
    )
    parser.add_argument(
        "--archive-username",
        default="admin",
        help="Usuário a registrar como arquivador técnico das duplicatas saneadas."
    )
    parser.add_argument(
        "--create-unique-index",
        action="store_true",
        help="Após aplicar o saneamento, cria o índice único parcial se não restarem duplicatas ativas."
    )
    parser.add_argument("--verbose", action="store_true", help="Mostra detalhes de cada grupo processado.")
    return parser.parse_args()


def parse_paths(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def dedupe_paths(paths: Iterable[str]) -> List[str]:
    seen = set()
    ordered = []
    for path in paths:
        normalized = str(path).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def text_or_none(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def timestamp_or_min(value: Optional[datetime]) -> float:
    if not value:
        return float("-inf")
    if value.tzinfo is None:
        return value.timestamp()
    return value.astimezone(timezone.utc).timestamp()


def date_or_min(value: Optional[date]) -> int:
    if not value:
        return -1
    return value.toordinal()


def has_documents(solicitacao: SolicitacaoCusta) -> bool:
    return bool(parse_paths(solicitacao.comprovantes_path))


def portal_status_rank(status_portal: Optional[str]) -> int:
    normalized = str(status_portal or "").lower()
    if not normalized:
        return 0
    if "efetivad" in normalized or "liquid" in normalized:
        return 500
    if any(term in normalized for term in ("cancel", "indefer", "devolv", "reprov", "recus")):
        return 450
    if "aguardando efetiva" in normalized or "process" in normalized:
        return 350
    if "aguardando confirma" in normalized:
        return 300
    if "cadastr" in normalized:
        return 250
    return 100


def robot_status_rank(status_robo: Optional[str]) -> int:
    normalized = str(status_robo or "").lower()
    if not normalized:
        return 0
    if "finalizado" in normalized:
        return 500
    if "alerta" in normalized:
        return 450
    if "monitorando" in normalized:
        return 350
    if "pendente" in normalized:
        return 250
    if "erro" in normalized:
        return 150
    return 100


def state_source_key(solicitacao: SolicitacaoCusta):
    return (
        1 if solicitacao.ultima_verificacao_robo else 0,
        1 if has_documents(solicitacao) else 0,
        1 if solicitacao.usuario_confirmacao_id else 0,
        portal_status_rank(solicitacao.status_portal),
        robot_status_rank(solicitacao.status_robo),
        timestamp_or_min(solicitacao.ultima_verificacao_robo),
        solicitacao.id,
    )


def canonical_key(solicitacao: SolicitacaoCusta):
    return (
        1 if not solicitacao.is_archived else 0,
        date_or_min(solicitacao.data_solicitacao),
        solicitacao.id,
    )


def choose_latest_value_source(rows: List[SolicitacaoCusta]) -> SolicitacaoCusta:
    return max(rows, key=canonical_key)


def choose_state_source(rows: List[SolicitacaoCusta]) -> SolicitacaoCusta:
    return max(rows, key=state_source_key)


def choose_latest_finalization(rows: List[SolicitacaoCusta]) -> Optional[SolicitacaoCusta]:
    finalized_rows = [row for row in rows if row.data_finalizacao]
    if not finalized_rows:
        return None
    return max(finalized_rows, key=lambda row: timestamp_or_min(row.data_finalizacao))


def latest_non_null_datetime(rows: List[SolicitacaoCusta], field_name: str):
    values = [getattr(row, field_name) for row in rows if getattr(row, field_name) is not None]
    if not values:
        return None
    return max(values, key=timestamp_or_min)


def latest_non_null_by_business_source(rows: List[SolicitacaoCusta], field_name: str):
    candidates = [row for row in rows if getattr(row, field_name) is not None]
    if not candidates:
        return None
    return max(candidates, key=canonical_key)


def sanitize_group(rows: List[SolicitacaoCusta], archive_user_id: Optional[int], apply_changes: bool):
    rows = sorted(rows, key=lambda row: row.id)
    active_rows = [row for row in rows if not row.is_archived]
    candidate_rows = active_rows or rows
    canonical = max(candidate_rows, key=canonical_key)
    state_source = choose_state_source(rows)
    latest_source = choose_latest_value_source(rows)
    latest_finalization = choose_latest_finalization(rows)
    losers = [row for row in rows if row.id != canonical.id]

    merged_paths = dedupe_paths(
        path
        for row in rows
        for path in parse_paths(row.comprovantes_path)
    )

    canonical.valor = latest_source.valor if latest_source.valor is not None else canonical.valor
    canonical.data_solicitacao = latest_source.data_solicitacao or canonical.data_solicitacao
    canonical.numero_processo = text_or_none(
        latest_source.numero_processo,
        state_source.numero_processo,
        canonical.numero_processo,
    )
    canonical.especificacao = text_or_none(
        latest_source.especificacao,
        state_source.especificacao,
        canonical.especificacao,
    )
    canonical.status_portal = text_or_none(state_source.status_portal, latest_source.status_portal, canonical.status_portal)
    canonical.status_robo = text_or_none(state_source.status_robo, latest_source.status_robo, canonical.status_robo)
    canonical.monitoramento_ativo = bool(state_source.monitoramento_ativo)
    canonical.motivo_encerramento = text_or_none(
        state_source.motivo_encerramento,
        latest_source.motivo_encerramento,
        canonical.motivo_encerramento,
    )
    canonical.ultima_verificacao_robo = latest_non_null_datetime(rows, "ultima_verificacao_robo")
    canonical.usuario_confirmacao_id = state_source.usuario_confirmacao_id or canonical.usuario_confirmacao_id
    canonical.proxima_verificacao_em = latest_non_null_datetime(rows, "proxima_verificacao_em")
    canonical.alerta_enviado_em = latest_non_null_datetime(rows, "alerta_enviado_em")
    canonical.prazo_fatal_em = (
        latest_non_null_by_business_source(rows, "prazo_fatal_em").prazo_fatal_em
        if latest_non_null_by_business_source(rows, "prazo_fatal_em")
        else canonical.prazo_fatal_em
    )
    canonical.acao_apos_alerta = text_or_none(
        latest_source.acao_apos_alerta,
        state_source.acao_apos_alerta,
        canonical.acao_apos_alerta,
    )
    canonical.aguardando_confirmacao = any(bool(row.aguardando_confirmacao) for row in rows)
    canonical.comprovantes_path = merged_paths or canonical.comprovantes_path
    if active_rows:
        canonical.is_archived = False
        canonical.data_arquivamento = None
        canonical.usuario_arquivamento_id = None

    canonical_status = str(canonical.status_robo or "").lower()
    canonical_is_open = canonical.monitoramento_ativo or "pendente" in canonical_status or "monitorando" in canonical_status
    if canonical_is_open:
        canonical.usuario_finalizacao_id = None
        canonical.data_finalizacao = None
    elif latest_finalization:
        canonical.usuario_finalizacao_id = latest_finalization.usuario_finalizacao_id
        canonical.data_finalizacao = latest_finalization.data_finalizacao

    now_utc = datetime.now(timezone.utc)
    archive_reason = ARCHIVE_REASON_TEMPLATE.format(canonical_id=canonical.id)

    for loser in losers:
        loser.is_archived = True
        loser.data_arquivamento = now_utc
        loser.usuario_arquivamento_id = archive_user_id
        loser.monitoramento_ativo = False
        loser.proxima_verificacao_em = None
        loser.alerta_enviado_em = None
        loser.status_robo = archive_reason
        loser.motivo_encerramento = archive_reason

    summary = {
        "npj": canonical.npj,
        "numero_solicitacao": canonical.numero_solicitacao,
        "canonical_id": canonical.id,
        "loser_ids": [row.id for row in losers],
        "merged_paths": len(merged_paths),
        "final_status_portal": canonical.status_portal,
        "final_status_robo": canonical.status_robo,
    }

    if apply_changes:
        return summary
    return summary


def ensure_unique_index() -> bool:
    with engine.begin() as conn:
        duplicate_exists = conn.exec_driver_sql(
            """
            SELECT 1
            FROM (
                SELECT npj, numero_solicitacao
                FROM solicitacoes_custas
                WHERE is_archived = FALSE
                GROUP BY npj, numero_solicitacao
                HAVING COUNT(*) > 1
            ) AS duplicadas
            LIMIT 1
            """
        ).scalar()
        if duplicate_exists:
            return False
        conn.exec_driver_sql(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX_NAME}
            ON solicitacoes_custas (npj, numero_solicitacao)
            WHERE is_archived = FALSE
            """
        )
    return True


def main():
    args = parse_args()
    db = SessionLocal()
    try:
        archive_user = db.query(User).filter(User.username == args.archive_username).first() if args.archive_username else None
        archive_user_id = archive_user.id if archive_user else None

        query = db.query(SolicitacaoCusta.npj, SolicitacaoCusta.numero_solicitacao, func.count().label("total"))
        if not args.include_archived_only:
            query = query.filter(SolicitacaoCusta.is_archived.is_(False))
        if args.npj:
            query = query.filter(SolicitacaoCusta.npj == args.npj)
        if args.numero_solicitacao:
            query = query.filter(SolicitacaoCusta.numero_solicitacao == args.numero_solicitacao)

        duplicate_keys = (
            query.group_by(SolicitacaoCusta.npj, SolicitacaoCusta.numero_solicitacao)
            .having(func.count() > 1)
            .order_by(func.count().desc(), SolicitacaoCusta.npj.asc())
        )

        if args.limit:
            duplicate_keys = duplicate_keys.limit(args.limit)

        duplicate_keys = duplicate_keys.all()

        if not duplicate_keys:
            print("Nenhum grupo duplicado encontrado com os filtros atuais.")
            if args.apply and args.create_unique_index:
                created = ensure_unique_index()
                print("Índice único parcial criado." if created else "Índice único parcial não criado; ainda existem duplicatas ativas.")
            return 0

        summaries = []
        losers_archived = 0
        status_counter = Counter()

        for npj, numero_solicitacao, total in duplicate_keys:
            row_query = db.query(SolicitacaoCusta).filter(
                SolicitacaoCusta.npj == npj,
                SolicitacaoCusta.numero_solicitacao == numero_solicitacao,
            )
            rows = row_query.order_by(SolicitacaoCusta.id.asc()).all()
            summary = sanitize_group(rows, archive_user_id, apply_changes=args.apply)
            summaries.append(summary)
            losers_archived += len(summary["loser_ids"])
            status_counter[str(summary["final_status_portal"] or "Sem status")] += 1

            if args.verbose or not args.apply:
                print(
                    f"{npj} / {numero_solicitacao}: manter ID {summary['canonical_id']} "
                    f"| arquivar {summary['loser_ids']} | portal={summary['final_status_portal'] or 'N/A'} "
                    f"| robo={summary['final_status_robo'] or 'N/A'}"
                )

        if args.apply:
            db.commit()
        else:
            db.rollback()

        print("")
        print(f"Grupos processados: {len(summaries)}")
        print(f"Registros excedentes tratados: {losers_archived}")
        print("Distribuição final de status_portal dos canônicos:")
        for status_label, total in status_counter.most_common():
            print(f"  - {status_label}: {total}")

        if args.apply and args.create_unique_index:
            created = ensure_unique_index()
            print("Índice único parcial criado." if created else "Índice único parcial não criado; ainda existem duplicatas ativas.")

        if not args.apply:
            print("")
            print("Dry-run finalizado. Rode novamente com --apply para gravar as mudanças.")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
