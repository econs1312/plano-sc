import streamlit as st
import pandas as pd
import datetime
import os
import io

from modules.anonymizer import gerar_codigo_caso, sanitizar_texto
from modules.gemini_extractor import extrair_evidencia_com_gemini
from modules.storage import init_db, salvar_caso, obter_resumo_estatistico, obter_todos_itens_df, exportar_para_excel

# Inicializar banco de dados local
init_db()

# -----------------------------------------------------------------------------
# Configuração da Página
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Levantamento Amostral - Plano SC",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS refinada
st.markdown("""
<style>
    /* =====================================================================
       BLINDAGEM VISUAL: Ocultar qualquer menção a GitHub, Streamlit e Desenvolvedor
       ===================================================================== */
    #MainMenu {visibility: hidden !important; display: none !important;}
    footer {visibility: hidden !important; display: none !important;}
    header {visibility: hidden !important; display: none !important;}
    
    div[data-testid="stToolbar"] {visibility: hidden !important; display: none !important;}
    div[data-testid="stDecoration"] {display: none !important;}
    div[data-testid="stStatusWidget"] {visibility: hidden !important; display: none !important;}
    .viewerBadge_container__1QSob {display: none !important;}
    button[title="View app in Streamlit Community Cloud"] {display: none !important;}
    
    /* Ajuste de espaçamento superior sem o header padrão */
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
    }

    /* Tipografia e componentes da pesquisa */
    .main-header {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        color: #1B4965;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #5C677D;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .card-box {
        background-color: #FFFFFF;
        border-radius: 8px;
        padding: 1.2rem;
        border: 1px solid #E0E1DD;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        margin-bottom: 1rem;
    }
    .badge-status {
        background-color: #E8F4F8;
        color: #1B4965;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
        display: inline-block;
    }
    .stButton>button {
        background-color: #1B4965;
        color: white;
        border-radius: 6px;
        font-weight: 600;
        border: none;
        padding: 0.5rem 1.2rem;
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
# Barra Lateral (Navegação e Contexto)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/medical-history.png", width=64)
    st.markdown("### **Estudo Atuarial & Pericial**")
    st.markdown("**Plano SC — Observatório Amostral**")
    st.caption("Iniciativa colaborativa independente voltada à pesquisa estatística e análise da composição de custos médicos.")
    
    st.divider()
    
    opcao_menu = st.radio(
        "Navegação:",
        ["📤 Colaborar com Evidência", "📈 Painel do Estudo", "📖 Metodologia & LGPD"],
        index=0
    )
    
    st.divider()
    
    # Resumo rápido na sidebar
    resumo_lateral = obter_resumo_estatistico()
    st.markdown("**Amostragem Consolidada:**")
    st.markdown(f"- 📁 **{resumo_lateral['total_casos']}** casos catalogados")
    st.markdown(f"- 📦 **{resumo_lateral['total_itens']}** itens de faturamento")
    if resumo_lateral['soma_coparticipacao'] > 0:
        st.markdown(f"- 💰 **R$ {resumo_lateral['soma_coparticipacao']:,.2f}** copart. amostrada")
        
    st.divider()
    st.caption("🔒 Ambiente seguro. Nenhum dado pessoal é transmitido ou armazenado.")

# -----------------------------------------------------------------------------
# ABA 1: Colaborar com Evidência (Intake com IA Gemini)
# -----------------------------------------------------------------------------
if opcao_menu == "📤 Colaborar com Evidência":
    st.markdown("<h2 class='main-header'>📤 Colaboração com o Levantamento de Faturamentos</h2>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>Envie extratos ou telas do aplicativo do Plano SC para extração automatizada via IA e inclusão na base de pesquisa estatística.</p>", unsafe_allow_html=True)
    
    # Validação da Chave
    if not api_key:
        st.warning("⚠️ Chave da API Gemini não configurada em secrets. Por favor, informe abaixo para prosseguir com a extração inteligente:")
        api_key = st.text_input("Chave API Gemini:", type="password")
        if not api_key:
            st.stop()
            
    with st.expander("ℹ️ Instruções para envio (Clique para expandir)", expanded=False):
        st.markdown("""
        1. **O que enviar:** Capturas de tela do extrato de coparticipação, 'Detalhes do Evento' ou extrato em PDF gerado no app do Plano SC.
        2. **Privacidade garantida:** Não se preocupe se o print contiver seu nome ou matrícula; a inteligência artificial suprime e tarja esses dados imediatamente.
        3. **Conferência humana:** Após o processamento da imagem, você poderá revisar a tabela de itens antes da gravação definitiva.
        """)

    # Etapa 1: Contexto Geral do Atendimento
    st.markdown("#### 1. Contexto do Atendimento")
    col1, col2, col3 = st.columns([1, 1.5, 1.5])
    
    with col1:
        uf_selecionada = st.selectbox(
            "UF do Atendimento:",
            ["SP", "DF", "RJ", "MG", "BA", "PR", "RS", "SC", "CE", "PE", "GO", "ES", "Outro/Nacional"],
            index=0
        )
    with col2:
        cidade_informada = st.text_input("Cidade (opcional):", placeholder="Ex: São Paulo, Campinas...")
    with col3:
        tipo_atendimento_selecionado = st.selectbox(
            "Tipo de Evento:",
            ["Pronto-Socorro / Emergência", "Internação Hospitalar", "Cirurgia / Procedimento", "Exames / SADT", "Consulta Eletiva", "Não tenho certeza"]
        )

    st.markdown("#### 2. Envio do Comprovante (Imagem ou PDF)")
    arquivo_enviado = st.file_uploader(
        "Selecione ou fotografe o extrato/tela do app (PNG, JPG ou PDF):",
        type=["png", "jpg", "jpeg", "pdf"],
        help="Permitido até 25MB por arquivo."
    )
    
    if arquivo_enviado is not None:
        col_img, col_proc = st.columns([1.2, 1.8])
        
        with col_img:
            st.markdown("**Prévia do Arquivo:**")
            if arquivo_enviado.type.startswith("image/"):
                st.image(arquivo_enviado, use_container_width=True)
            else:
                st.info(f"📄 Documento PDF anexado: {arquivo_enviado.name} ({arquivo_enviado.size / 1024:.1f} KB)")
                
        with col_proc:
            st.markdown("**Processamento com IA Gemini:**")
            st.caption("O Gemini analisará as linhas de insumos, medicamentos, taxas e exames com leitura multimodal.")
            
            if st.button("🔍 Extrair Itens com IA Gemini", key="btn_extrair"):
                with st.spinner("Analisando comprovante e aplicando regras de anonimização com Gemini..."):
                    bytes_arquivo = arquivo_enviado.getvalue()
                    resultado = extrair_evidencia_com_gemini(
                        arquivo_bytes=bytes_arquivo,
                        mime_type=arquivo_enviado.type,
                        api_key=api_key
                    )
                    
                    if resultado["sucesso"]:
                        st.session_state["dados_extraidos"] = resultado["dados"]
                        st.session_state["modelo_usado"] = resultado["modelo_usado"]
                        st.session_state["arquivo_nome"] = arquivo_enviado.name
                        st.success(f"Extração concluída com sucesso via {resultado['modelo_usado']}!")
                    else:
                        st.error(f"Erro na extração: {resultado.get('erro')}")

    # Etapa 3: Validação dos Dados Extraídos
    if "dados_extraidos" in st.session_state and st.session_state["dados_extraidos"]:
        dados = st.session_state["dados_extraidos"]
        itens = dados.get("itens", [])
        
        st.divider()
        st.markdown("#### 3. Conferência e Validação dos Itens")
        st.caption("Revise os valores identificados pela IA. Você pode editar diretamente nas células da tabela abaixo se houver alguma divergência:")
        
        c_hosp, c_data = st.columns(2)
        with c_hosp:
            hosp_val = st.text_input("Prestador / Hospital Identificado:", value=dados.get("hospital_ou_prestador", "Não informado"))
        with c_data:
            data_val = st.text_input("Data do Evento Identificada:", value=dados.get("data_evento", ""))
            
        if itens:
            # Converter itens em DataFrame editável
            df_itens = pd.DataFrame(itens)
            # Garantir colunas necessárias
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
                    "observacao_estatistica": st.column_config.TextColumn("Observação Estatística")
                },
                use_container_width=True,
                num_rows="dynamic"
            )
            
            # Totais
            total_copart = df_editado["coparticipacao"].sum()
            total_fat = df_editado["faturado_credenciado"].sum()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total de Itens", len(df_editado))
            m2.metric("Coparticipação Total", f"R$ {total_copart:,.2f}")
            m3.metric("Faturado pelo Prestador", f"R$ {total_fat:,.2f}")
            
            st.divider()
            
            # Termo de Consentimento LGPD
            st.markdown("#### 4. Autorização de Uso Acadêmico/Estatístico")
            concorda_lgpd = st.checkbox(
                "Declaro que sou o titular ou dependente deste comprovante e autorizo a utilização anônima e desidentificada destes valores exclusivamente para fins de estudo estatístico, pesquisa atuarial e perícia coletiva sobre o Plano SC.",
                value=False
            )
            
            if st.button("💾 Confirmar e Registrar na Base do Estudo", type="primary", disabled=not concorda_lgpd):
                codigo_caso = gerar_codigo_caso(uf_selecionada)
                caso_info = {
                    "codigo_caso": codigo_caso,
                    "uf": uf_selecionada,
                    "cidade": sanitizar_texto(cidade_informada),
                    "hospital_prestador": sanitizar_texto(hosp_val),
                    "tipo_atendimento": tipo_atendimento_selecionado,
                    "data_evento": sanitizar_texto(data_val)
                }
                
                itens_finais = df_editado.to_dict(orient="records")
                salvar_caso(caso_info, itens_finais)
                
                st.balloons()
                st.success(f"✅ Evidência registrada com sucesso sob o protocolo anônimo **{codigo_caso}**!")
                st.info("Agradecemos imensamente pela colaboração com a pesquisa coletiva do Plano SC. Seus dados fortalecem o estudo.")
                
                # Limpar estado
                del st.session_state["dados_extraidos"]
                st.button("Enviar Novo Comprovante")
        else:
            st.info("Nenhum item discriminado foi identificado na imagem. Verifique se o print contém a lista detalhada de eventos.")

# -----------------------------------------------------------------------------
# ABA 2: Painel do Estudo (Visualização e Exportação)
# -----------------------------------------------------------------------------
elif opcao_menu == "📈 Painel do Estudo":
    st.markdown("<h2 class='main-header'>📈 Painel Consolidado de Amostragem</h2>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>Indicadores agregados em tempo real sobre os faturamentos e coparticipações coletados.</p>", unsafe_allow_html=True)
    
    resumo = obter_resumo_estatistico()
    
    # Cartões de Métricas
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dossiês Coletados", f"{resumo['total_casos']}")
    c2.metric("Itens Mapeados", f"{resumo['total_itens']}")
    c3.metric("Coparticipação Amostrada", f"R$ {resumo['soma_coparticipacao']:,.2f}")
    c4.metric("Faturamento Credenciado", f"R$ {resumo['soma_faturado']:,.2f}")
    
    st.divider()
    
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("##### 📍 Distribuição de Casos por UF")
        if not resumo["df_uf"].empty:
            st.bar_chart(resumo["df_uf"].set_index("uf")["total_casos"])
        else:
            st.info("Ainda não há registros por estado.")
            
    with g2:
        st.markdown("##### 🏷️ Itens por Categoria de Despesa")
        if not resumo["df_categoria"].empty:
            st.bar_chart(resumo["df_categoria"].set_index("categoria")["qtd"])
        else:
            st.info("Ainda não há categorias registradas.")
            
    st.divider()
    
    st.markdown("#### 📥 Tabela Consolidada & Exportação Pericial")
    df_completo = obter_todos_itens_df()
    
    if not df_completo.empty:
        st.dataframe(df_completo, use_container_width=True, height=350)
        
        # Botão de Download Excel
        excel_bytes = exportar_para_excel()
        st.download_button(
            label="📊 Baixar Base Completa em Excel (.xlsx)",
            data=excel_bytes,
            file_name=f"Base_Levantamento_Amostral_Plano_SC_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("A base de dados ainda está vazia. Utilize a aba de colaboração para cadastrar os primeiros casos.")

# -----------------------------------------------------------------------------
# ABA 3: Metodologia & LGPD
# -----------------------------------------------------------------------------
elif opcao_menu == "📖 Metodologia & LGPD":
    st.markdown("<h2 class='main-header'>📖 Metodologia, Rigor Pericial & LGPD</h2>", unsafe_allow_html=True)
    st.markdown("""
    ### 1. Finalidade Exclusiva da Pesquisa
    Este ambiente tem como objetivo exclusivo o **levantamento estatístico amostral** de contas médicas e demonstrativos de coparticipação decorrentes de atendimentos cobertos pelo **Plano SC**.
    
    A iniciativa é estritamente técnica, neutra e sem qualquer conotação alarmista ou punitiva. O propósito consiste em:
    - Mapear a representatividade de cada categoria de custo (materiais de consumo, medicamentos, dispositivos especiais, taxas);
    - Avaliar a consistência das cobranças de coparticipação em relação a padrões de mercado e boas práticas de gestão de saúde;
    - Subsidiar análises atuariais e estudos periciais com embasamento matemático e documental.

    ---

    ### 2. Governança e Anonimização Estrita (LGPD)
    Em estrito cumprimento à Lei Geral de Proteção de Dados (Lei nº 13.709/2018):
    - **Nenhum Dado Sensível Identificável:** Não são coletados nem armazenados nomes de beneficiários, telefones, números de CPF, matrículas corporativas ou dados clínicos individuais.
    - **Tarjamento Prévio:** Os comprovantes enviados são processados por rotinas automáticas com algoritmos de mascaramento de texto antes de qualquer inclusão em banco.
    - **Codificação por Dossiês:** Cada colaboração recebe um código anônimo aleatório (ex: CASO-SC-SP-2026-A1B2) e é desvinculada de qualquer remetente.

    ---

    ### 3. Integração com o Pipeline de Auditoria de Mercado
    A base consolidada gerada por este formulário alimenta diretamente os modelos paramétricos de auditoria pericial, sendo cotejada contra fontes públicas oficiais e de distribuição hospitalar:
    - **CMED / ANVISA:** Tabela de Preço Fabricante (PF) e Preço Máximo ao Consumidor (PMC);
    - **SIMPRO / Brasíndice:** Referenciais de medicamentos e insumos hospitalares;
    - **Tabelas de Distribuidores:** Valores de aquisição e comodato de dispositivos médicos especiais.
    """)

