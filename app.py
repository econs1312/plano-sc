import streamlit as st
import pandas as pd
import datetime
import os
import io

from modules.anonymizer import gerar_codigo_caso, sanitizar_texto
from modules.gemini_extractor import extrair_evidencia_com_gemini, transcrever_audio_com_gemini
from modules.storage import init_db, salvar_caso, obter_resumo_estatistico, obter_todos_itens_df, exportar_para_excel

# Inicializar banco de dados local
init_db()

# -----------------------------------------------------------------------------
# Configuração da Página: Centralizada, sem sidebar e sem menu
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Colaboração de Extratos - Plano SC",
    page_icon="📋",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Estilização CSS: Eliminação total de menus, rodapés e barras laterais
st.markdown("""
<style>
    /* Ocultar completamente a barra lateral e menus do Streamlit */
    section[data-testid="stSidebar"] {display: none !important;}
    div[data-testid="collapsedControl"] {display: none !important;}
    #MainMenu {visibility: hidden !important; display: none !important;}
    footer {visibility: hidden !important; display: none !important;}
    header {visibility: hidden !important; display: none !important;}
    div[data-testid="stToolbar"] {visibility: hidden !important; display: none !important;}
    div[data-testid="stDecoration"] {display: none !important;}
    div[data-testid="stStatusWidget"] {visibility: hidden !important; display: none !important;}
    .viewerBadge_container__1QSob {display: none !important;}
    button[title="View app in Streamlit Community Cloud"] {display: none !important;}
    a[href*="share.streamlit.io/user"] {display: none !important;}
    
    /* Espaçamento agradável para formulário mobile */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 4rem !important;
        max-width: 760px !important;
    }

    .main-title {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        color: #1B4965;
        font-weight: 700;
        font-size: 1.8rem;
        margin-bottom: 0.3rem;
    }
    .sub-title {
        color: #5C677D;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
        line-height: 1.4;
    }
    .notice-box {
        background-color: #F0F4F8;
        border-left: 4px solid #1B4965;
        padding: 0.9rem 1.1rem;
        border-radius: 4px;
        margin-bottom: 1.5rem;
        font-size: 0.92rem;
        color: #2B2D42;
    }
    .stButton>button {
        background-color: #1B4965;
        color: white;
        border-radius: 6px;
        font-weight: 600;
        border: none;
        padding: 0.6rem 1.5rem;
    }
    .stButton>button:hover {
        background-color: #133549;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Recuperação Segura da Chave Gemini
# -----------------------------------------------------------------------------
api_key = ""
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
elif "GEMINI_API_KEY" in os.environ:
    api_key = os.environ["GEMINI_API_KEY"]

# -----------------------------------------------------------------------------
# Verificar Modo Administrativo Oculto (Acessado apenas via ?admin=1 na URL)
# -----------------------------------------------------------------------------
query_params = st.query_params
modo_admin = query_params.get("admin", "").lower() in ["1", "true", "sim"]

if modo_admin:
    st.markdown("### 🔐 Painel Restrito de Curadoria")
    senha = st.text_input("Informe a chave de acesso:", type="password")
    admin_pass = st.secrets.get("ADMIN_PASSWORD", "pesquisa_plano_sc")
    
    if senha == admin_pass:
        resumo = obter_resumo_estatistico()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Casos", f"{resumo['total_casos']}")
        col2.metric("Itens", f"{resumo['total_itens']}")
        col3.metric("Copart. Total", f"R$ {resumo['soma_coparticipacao']:,.2f}")
        col4.metric("Origem dos Dados", resumo.get("fonte", "Local"))
        
        st.divider()
        df_completo = obter_todos_itens_df()
        if not df_completo.empty:
            st.dataframe(df_completo, use_container_width=True)
            excel_bytes = exportar_para_excel()
            st.download_button(
                label="📊 Baixar Base Completa em Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"Base_Levantamento_Amostral_Plano_SC_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("A base de dados ainda não possui registros.")
    else:
        if senha:
            st.error("Chave de acesso incorreta.")
    st.stop()

# -----------------------------------------------------------------------------
# INTERFACE PRINCIPAL: Formulário Único de Recepção de Dados
# -----------------------------------------------------------------------------
st.markdown("<div class='main-title'>📋 Levantamento Colaborativo de Extratos</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>Espaço colaborativo para reunir demonstrativos e extratos de atendimentos. O objetivo é organizar dúvidas frequentes e exemplos práticos para apresentar ao Conselho de Usuários do Plano SC.</div>", unsafe_allow_html=True)

st.markdown("""
<div class='notice-box'>
    🔒 <strong>Privacidade Total (LGPD):</strong> Não coletamos nomes, matrículas ou dados pessoais. As imagens passam por leitura automática que extrai apenas os procedimentos e valores para organização coletiva.
</div>
""", unsafe_allow_html=True)

# 1. Contexto do Atendimento
st.markdown("#### 1. Contexto Geral")
col_uf, col_cid, col_tipo = st.columns([1, 1.5, 2])

with col_uf:
    uf_selecionada = st.selectbox(
        "UF:",
        ["SP", "DF", "RJ", "MG", "BA", "PR", "RS", "SC", "CE", "PE", "GO", "ES", "Outro/Nacional"],
        index=0
    )
with col_cid:
    cidade_informada = st.text_input("Cidade (opcional):", placeholder="Ex: Campinas")
with col_tipo:
    tipo_atendimento_selecionado = st.selectbox(
        "Tipo de Atendimento:",
        ["Pronto-Socorro / Emergência", "Internação Hospitalar", "Cirurgia / Procedimento", "Exames / SADT", "Consulta Eletiva", "Outro / Não sei informar"]
    )

natureza_inconsistencia_selecionada = st.selectbox(
    "Principal Situação Observada:",
    [
        "Valores Fora da Curva (preços muito acima da média de mercado)",
        "Cobrança Indevida (duplicidade, erro de lançamento ou procedimento não realizado)",
        "Cobrança Avulsa de Itens Básicos (agulhas, luvas, algodão cobrados à parte)",
        "Coparticipação Elevada (valor retido desproporcional ao atendimento)",
        "Outra Dúvida / Envio Geral de Extrato"
    ],
    help="Ajuda a organizar as consultas por tema para apresentação ao Conselho de Usuários."
)

# 2. Upload do Comprovante
st.markdown("#### 2. Anexo do Comprovante")
st.caption("Envie capturas de tela do extrato de coparticipação, 'Detalhes do Evento' no app ou arquivo PDF:")

arquivo_enviado = st.file_uploader(
    "Carregar imagem ou documento (JPG, PNG ou PDF):",
    type=["png", "jpg", "jpeg", "pdf"],
    label_visibility="collapsed"
)

if arquivo_enviado is not None:
    st.write("")
    if st.button("🔍 Identificar Itens do Comprovante", type="primary", use_container_width=True):
        if not api_key:
            st.error("Chave da API Gemini não configurada.")
            st.stop()
            
        with st.spinner("Identificando procedimentos e valores no comprovante..."):
            bytes_arquivo = arquivo_enviado.getvalue()
            resultado = extrair_evidencia_com_gemini(
                arquivo_bytes=bytes_arquivo,
                mime_type=arquivo_enviado.type,
                api_key=api_key
            )
            
            if resultado["sucesso"]:
                st.session_state["dados_extraidos"] = resultado["dados"]
                st.success("Comprovante processado com sucesso!")
            else:
                st.error(f"Erro no processamento: {resultado.get('erro')}")

# 3. Conferência e Validação dos Dados
if "dados_extraidos" in st.session_state and st.session_state["dados_extraidos"]:
    dados = st.session_state["dados_extraidos"]
    itens = dados.get("itens", [])
    
    st.divider()
    st.markdown("#### 3. Conferência dos Itens Identificados")
    st.caption("Revise os valores identificados. Você pode editar diretamente nas células da tabela se desejar ajustar algo:")
    
    c_hosp, c_data = st.columns(2)
    with c_hosp:
        hosp_val = st.text_input("Hospital / Prestador Identificado:", value=dados.get("hospital_ou_prestador", "Não informado"))
    with c_data:
        data_val = st.text_input("Data do Evento:", value=dados.get("data_evento", ""))
        
    if itens:
        df_itens = pd.DataFrame(itens)
        for col in ["descricao", "categoria", "quantidade", "coparticipacao", "faturado_credenciado", "observacao_estatistica"]:
            if col not in df_itens.columns:
                df_itens[col] = "" if col in ["descricao", "categoria", "observacao_estatistica"] else 0.0
                
        df_editado = st.data_editor(
            df_itens,
            column_config={
                "descricao": st.column_config.TextColumn("Descrição do Item", width="large", required=True),
                "categoria": st.column_config.SelectboxColumn(
                    "Categoria",
                    options=[
                        "Dispositivos / Insumos Especiais",
                        "Materiais de Consumo Básico",
                        "Medicamentos / Soluções",
                        "Exames e Diagnósticos",
                        "Consultas / Pronto-Socorro",
                        "Taxas e Diárias",
                        "Outros"
                    ],
                    required=True
                ),
                "quantidade": st.column_config.NumberColumn("Qtd", min_value=0.1, step=1.0, format="%.1f"),
                "coparticipacao": st.column_config.NumberColumn("Coparticipação (R$)", min_value=0.0, format="R$ %.2f"),
                "faturado_credenciado": st.column_config.NumberColumn("Faturado Credenciado (R$)", min_value=0.0, format="R$ %.2f"),
                "observacao_estatistica": st.column_config.TextColumn("Observação / Detalhe")
            },
            use_container_width=True,
            num_rows="dynamic"
        )
        
        tot_copart = df_editado["coparticipacao"].sum()
        tot_fat = df_editado["faturado_credenciado"].sum()
        
        m1, m2 = st.columns(2)
        m1.metric("Coparticipação Informada", f"R$ {tot_copart:,.2f}")
        m2.metric("Total Faturado pelo Prestador", f"R$ {tot_fat:,.2f}")
        
        st.write("")
        # 4. Relato e Identificação (Opcionais)
        st.markdown("#### 4. Relato e Identificação (Opcionais)")
        
        relato_escrito = st.text_area(
            "Breve Relato ou Observações (Opcional):",
            placeholder="Conte brevemente o contexto do atendimento, se houve negativa, cobrança inesperada de insumos ou dúvida em algum item...",
            help="Espaço para descrever particularidades que não aparecem no comprovante."
        )

        st.caption("🎙️ **Ou se preferir, grave um áudio pelo microfone (Opcional):**")
        audio_gravado = st.audio_input("Gravar relato em áudio:", label_visibility="collapsed")
        
        audio_transcrito_texto = ""
        if audio_gravado is not None:
            audio_hash = f"audio_{audio_gravado.size}_{arquivo_enviado.name}"
            if st.session_state.get("ultimo_audio_hash") != audio_hash:
                with st.spinner("Transcrevendo seu relato em áudio com IA..."):
                    transcricao = transcrever_audio_com_gemini(
                        audio_bytes=audio_gravado.getvalue(),
                        mime_type=audio_gravado.type or "audio/wav",
                        api_key=api_key
                    )
                    st.session_state["audio_transcricao"] = transcricao
                    st.session_state["ultimo_audio_hash"] = audio_hash
            
            if st.session_state.get("audio_transcricao"):
                st.info(f"📝 **Transcrição automática do áudio:** \"{st.session_state['audio_transcricao']}\"")
                audio_transcrito_texto = st.session_state["audio_transcricao"]

        matricula_opcional = st.text_input(
            "Matrícula ou Contato (Opcional):",
            placeholder="Ex: c123456 ou e-mail/telefone (deixe em branco se preferir anonimato total)",
            help="Campo estritamente opcional. Preencha apenas se desejar retorno ou acompanhamento junto ao Conselho de Usuários. Se deixar em branco, o envio será 100% anônimo."
        )

        concorda = st.checkbox(
            "Autorizo o compartilhamento destas informações de procedimentos e valores para compor a pauta de esclarecimentos junto ao Conselho de Usuários do Plano SC.",
            value=False
        )
        
        if st.button("📤 Enviar Informações", type="primary", use_container_width=True, disabled=not concorda):
            codigo_caso = gerar_codigo_caso(uf_selecionada)
            
            relato_partes = []
            if relato_escrito.strip():
                relato_partes.append(sanitizar_texto(relato_escrito.strip()))
            if audio_transcrito_texto.strip():
                relato_partes.append(f"[Áudio Transcrito]: {audio_transcrito_texto.strip()}")
            relato_final = " | ".join(relato_partes)
            
            caso_info = {
                "codigo_caso": codigo_caso,
                "uf": uf_selecionada,
                "cidade": sanitizar_texto(cidade_informada),
                "hospital_prestador": sanitizar_texto(hosp_val),
                "tipo_atendimento": tipo_atendimento_selecionado,
                "natureza_inconsistencia": natureza_inconsistencia_selecionada,
                "data_evento": sanitizar_texto(data_val),
                "identificacao_opcional": matricula_opcional.strip(),
                "relato_observacoes": relato_final
            }
            
            itens_finais = df_editado.to_dict(orient="records")
            resultado_salvamento = salvar_caso(caso_info, itens_finais)
            
            st.balloons()
            if matricula_opcional.strip():
                st.success(f"✅ Informações registradas com sucesso sob o protocolo **{codigo_caso}** (com identificação registrada).")
            else:
                st.success(f"✅ Informações registradas com sucesso sob o protocolo anônimo: **{codigo_caso}**")
            
            if resultado_salvamento.get("gsheets_sincronizado"):
                st.info("☁️ **Sincronização em Nuvem:** Dados salvos em tempo real na planilha do Google Drive.")
            
            st.info("Muito obrigado pela colaboração! Suas informações ajudarão a embasar as consultas junto ao Conselho de Usuários do Plano SC.")
            
            del st.session_state["dados_extraidos"]
            if st.button("Enviar Outro Comprovante"):
                st.rerun()
    else:
        st.warning("Nenhum item com valores foi discriminado automaticamente. Verifique se o print enviado contém o extrato detalhado.")




