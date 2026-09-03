from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from desmembramentos import processar_desmembramentos
from tarefas_background import acompanhar_tarefa, obter_gerenciador_tarefas

st.set_page_config(page_title="Desmembramento", layout="wide")

st.markdown(
    """
    <style>
    .block-container {max-width: 1320px; padding-top: 1.6rem; padding-bottom: 4rem;}
    .hero-desm {
        padding: 1.8rem 2rem; border-radius: 22px; margin-bottom: 1.2rem;
        background: linear-gradient(135deg, #25233f 0%, #47366f 55%, #7657b5 100%);
        box-shadow: 0 18px 45px rgba(0,0,0,.18); color: white;
    }
    .hero-desm h1 {font-size: 2.15rem; margin: 0 0 .4rem; color: white;}
    .hero-desm p {font-size: 1rem; margin: 0; opacity: .90; max-width: 880px;}
    .metric-card {
        border: 1px solid rgba(128,128,128,.20); border-radius: 16px;
        padding: .95rem 1rem; text-align:center; min-height: 94px;
        background: rgba(128,128,128,.04);
    }
    .metric-card .label {font-size:.78rem; opacity:.72; margin-bottom:.2rem;}
    .metric-card .value {font-size:1.55rem; font-weight:800;}
    .photo-title {font-weight:800; font-size:1.04rem; margin-bottom:.35rem;}
    .photo-sub {opacity:.68; font-size:.84rem; margin-bottom:.6rem;}
    div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {
        min-height: 3rem; border-radius: 12px; font-weight: 700;
    }
    @media (max-width: 720px) {.hero-desm{padding:1.4rem}.hero-desm h1{font-size:1.7rem}}
    </style>
    <div class="hero-desm">
      <h1>Desmembramento</h1>
      <p>Compare matrícula A x matrícula B foto por foto. O HASH atual continua sendo o método oficial; DINOv2 + ORB entram como auditoria paralela.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def executar(arquivo_bytes: bytes, progresso):
    resultado = processar_desmembramentos(BytesIO(arquivo_bytes), progresso=progresso)
    csv = resultado.to_csv(index=False, sep=";").encode("utf-8-sig")
    return resultado, csv


def _pct(valor):
    if valor is None:
        return None
    texto = str(valor).strip().replace("%", "").replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _fmt_pct(valor):
    n = _pct(valor)
    return f"{n:.1f}%" if n is not None else "—"


def _mostrar_imagem(url: str, legenda: str):
    url = str(url or "").strip()
    if not url or url.lower() in {"nan", "none", "<na>"}:
        st.info("Sem imagem disponível para este lado.")
        return
    try:
        st.image(url, caption=legenda, use_container_width=True)
    except Exception:
        st.warning("Não foi possível abrir a imagem diretamente.")
        st.code(url)


with st.container(border=True):
    st.subheader("Enviar base para processamento")
    st.caption("Formatos aceitos: Excel (.xlsx ou .xls) e CSV (.csv)")
    arquivo = st.file_uploader(
        "Selecione a base",
        type=["xlsx", "xls", "csv"],
        label_visibility="collapsed",
        key="arquivo_desmembramentos",
    )

if arquivo is None:
    st.info("📂 Selecione uma base para iniciar o processamento.")
else:
    st.caption(f"✓ {arquivo.name}  •  {arquivo.size / (1024 * 1024):.1f} MB")
    if st.button("Processar base", type="primary", use_container_width=True):
        st.session_state.pop("desmembramentos_resultado", None)
        st.session_state["audit_idx"] = 0
        gerenciador = obter_gerenciador_tarefas()
        tarefa_id = gerenciador.iniciar(executar, arquivo.getvalue())
        st.session_state["tarefa_desmembramento"] = tarefa_id
        st.query_params["tarefa_desmembramento"] = tarefa_id


tarefa_desmembramento = (
    st.session_state.get("tarefa_desmembramento")
    or st.query_params.get("tarefa_desmembramento")
)

if tarefa_desmembramento and "desmembramentos_resultado" not in st.session_state:
    try:
        resultado, csv_saida = acompanhar_tarefa(tarefa_desmembramento)
        st.session_state["desmembramentos_resultado"] = resultado
        st.session_state["desmembramentos_csv"] = csv_saida
        st.session_state.pop("tarefa_desmembramento", None)
        st.query_params.pop("tarefa_desmembramento", None)
        nome_base = Path(arquivo.name).stem if arquivo is not None else "base"
        st.session_state["desmembramentos_nome"] = f"{nome_base}_desmembramento.csv"
        st.session_state["audit_idx"] = 0
    except Exception as erro:
        st.session_state.pop("tarefa_desmembramento", None)
        st.query_params.pop("tarefa_desmembramento", None)
        if str(erro) == "A tarefa não está mais disponível no servidor.":
            st.info("A tarefa anterior expirou após uma reinicialização do servidor. Envie o arquivo novamente.")
        else:
            st.error(f"Não foi possível processar o arquivo: {erro}")


if "desmembramentos_resultado" in st.session_state:
    resultado = st.session_state["desmembramentos_resultado"]
    st.success(f"{len(resultado):,} registros processados.".replace(",", "."))

    aba_auditoria, aba_tabela, aba_base = st.tabs([
        "🖼️ Auditoria foto x foto",
        "📊 Comparações",
        "📄 Prévia da base",
    ])

    with aba_auditoria:
        obrigatorias = [
            "Auditoria_Matricula_A", "Auditoria_Matricula_B",
            "Auditoria_Foto_A", "Auditoria_Foto_B",
            "Similaridade_Atual_HASH", "Similaridade_DINOv2",
            "Similaridade_ORB_Estrutural", "Similaridade_Nova_Experimental",
            "Divergencia_Atual_vs_Nova",
        ]
        faltando = [c for c in obrigatorias if c not in resultado.columns]

        if faltando:
            st.warning("A base foi processada por uma versão anterior do módulo. Substitua também o desmembramentos.py pelo arquivo novo.")
        else:
            audit = resultado.copy()
            audit["_atual"] = audit["Similaridade_Atual_HASH"].apply(_pct)
            audit["_novo"] = audit["Similaridade_Nova_Experimental"].apply(_pct)
            audit["_div"] = audit["Divergencia_Atual_vs_Nova"].apply(_pct)

            # Mantém somente linhas que realmente têm uma matrícula A x B registrada.
            audit = audit[
                audit["Auditoria_Matricula_A"].astype(str).str.strip().ne("")
                & audit["Auditoria_Matricula_B"].astype(str).str.strip().ne("")
            ].copy()

            # O mesmo par pode aparecer na linha A e na linha B. Mostramos uma vez só.
            audit["_chave_par"] = audit.apply(
                lambda r: "||".join(sorted([
                    str(r["Auditoria_Matricula_A"]),
                    str(r["Auditoria_Matricula_B"]),
                ])) + "||" + str(r.get("Auditoria_Foto_A", "")) + "||" + str(r.get("Auditoria_Foto_B", "")),
                axis=1,
            )
            audit = audit.drop_duplicates("_chave_par")

            f1, f2, f3, f4 = st.columns([1, 1, 1, 1.25])
            with f1:
                minimo_atual = st.slider("HASH atual mínimo", 0, 100, 70, 5)
            with f2:
                minimo_div = st.slider("Divergência mínima", 0, 100, 0, 5)
            with f3:
                somente_apontados = st.checkbox("Só apontados", value=True)
            with f4:
                busca = st.text_input("Buscar matrícula", placeholder="Ex.: MC001234")

            audit = audit[audit["_atual"].fillna(-1) >= minimo_atual]
            audit = audit[audit["_div"].fillna(-1) >= minimo_div]
            if somente_apontados and "Status_Validacao" in audit.columns:
                audit = audit[audit["Status_Validacao"].astype(str) != "✅ OK"]
            if busca.strip():
                b = busca.strip().upper()
                audit = audit[
                    audit["Auditoria_Matricula_A"].astype(str).str.upper().str.contains(b, na=False)
                    | audit["Auditoria_Matricula_B"].astype(str).str.upper().str.contains(b, na=False)
                ]

            audit = audit.sort_values(["_div", "_atual"], ascending=[False, False], na_position="last").reset_index(drop=True)

            if audit.empty:
                st.info("Nenhum par encontrado com esses filtros.")
            else:
                total = len(audit)
                idx = int(st.session_state.get("audit_idx", 0))
                idx = max(0, min(idx, total - 1))
                st.session_state["audit_idx"] = idx

                nav1, nav2, nav3 = st.columns([1, 2, 1])
                with nav1:
                    if st.button("⬅️ Anterior", use_container_width=True, disabled=idx <= 0):
                        st.session_state["audit_idx"] = max(0, idx - 1)
                        st.rerun()
                with nav2:
                    novo_idx = st.number_input(
                        "Caso",
                        min_value=1,
                        max_value=total,
                        value=idx + 1,
                        step=1,
                        label_visibility="collapsed",
                    )
                    if novo_idx - 1 != idx:
                        st.session_state["audit_idx"] = int(novo_idx - 1)
                        st.rerun()
                    st.caption(f"Caso {idx + 1} de {total}")
                with nav3:
                    if st.button("Próximo ➡️", use_container_width=True, disabled=idx >= total - 1):
                        st.session_state["audit_idx"] = min(total - 1, idx + 1)
                        st.rerun()

                row = audit.iloc[idx]
                mat_a = str(row["Auditoria_Matricula_A"])
                mat_b = str(row["Auditoria_Matricula_B"])
                tipo_a = str(row.get("Auditoria_Tipo_Foto_A", "A"))
                tipo_b = str(row.get("Auditoria_Tipo_Foto_B", "B"))

                st.markdown(f"### Matrícula A: `{mat_a}`  ×  Matrícula B: `{mat_b}`")
                if "Status_Validacao" in row:
                    st.caption(f"Status: {row['Status_Validacao']}  •  Melhor par: {row.get('Auditoria_Melhor_Par', '')}")

                foto_a, foto_b = st.columns(2, gap="large")
                with foto_a:
                    st.markdown(f'<div class="photo-title">Matrícula A — {mat_a}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="photo-sub">Foto selecionada: {tipo_a}</div>', unsafe_allow_html=True)
                    _mostrar_imagem(row["Auditoria_Foto_A"], f"{mat_a} • {tipo_a}")
                with foto_b:
                    st.markdown(f'<div class="photo-title">Matrícula B — {mat_b}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="photo-sub">Foto selecionada: {tipo_b}</div>', unsafe_allow_html=True)
                    _mostrar_imagem(row["Auditoria_Foto_B"], f"{mat_b} • {tipo_b}")

                m1, m2, m3, m4, m5 = st.columns(5)
                cards = [
                    (m1, "HASH atual", row["Similaridade_Atual_HASH"]),
                    (m2, "DINOv2", row["Similaridade_DINOv2"]),
                    (m3, "ORB estrutural", row["Similaridade_ORB_Estrutural"]),
                    (m4, "Novo experimental", row["Similaridade_Nova_Experimental"]),
                    (m5, "Divergência", row["Divergencia_Atual_vs_Nova"]),
                ]
                for col, label, value in cards:
                    with col:
                        st.markdown(
                            f'<div class="metric-card"><div class="label">{label}</div><div class="value">{_fmt_pct(value)}</div></div>',
                            unsafe_allow_html=True,
                        )

                if "Detalhe_Inconsistencia" in row and str(row["Detalhe_Inconsistencia"]).strip():
                    st.info(str(row["Detalhe_Inconsistencia"]))

                st.caption(
                    "O HASH atual continua responsável pelos status nesta versão. A imagem exibida é o melhor par real A x B segundo o score experimental; DINO e ORB mostrados pertencem a esse mesmo par."
                )

    with aba_tabela:
        cols = [c for c in [
            "Auditoria_Matricula_A", "Auditoria_Matricula_B", "Auditoria_Melhor_Par",
            "Status_Validacao", "Similaridade_Atual_HASH", "Similaridade_DINOv2",
            "Similaridade_ORB_Estrutural", "Similaridade_Nova_Experimental",
            "Divergencia_Atual_vs_Nova", "Detalhe_Inconsistencia",
        ] if c in resultado.columns]
        st.dataframe(resultado[cols].head(1000), use_container_width=True, hide_index=True)

    with aba_base:
        st.caption("Primeiros 100 registros. O CSV contém a base completa.")
        st.dataframe(resultado.head(100), use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Baixar CSV processado",
        data=st.session_state["desmembramentos_csv"],
        file_name=st.session_state["desmembramentos_nome"],
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )
