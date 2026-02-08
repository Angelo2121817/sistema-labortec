elif menu == "📦 Estoque":
    st.title("📦 Estoque")
    
    # 1. Garante que o Saldo é número
    if not st.session_state["estoque"].empty:
        st.session_state["estoque"]["Saldo"] = pd.to_numeric(st.session_state["estoque"]["Saldo"], errors='coerce').fillna(0)

    # 2. Estilização: Fundo VERDE e Texto VERDE ESCURO
    def estilo_saldo(val):
        # background-color: #d4edda (Verde Claro)
        # color: #155724 (Verde Escuro)
        return 'background-color: #d4edda; color: #155724; font-weight: 900; border: 1px solid #c3e6cb'

    # Aplica o estilo
    # Nota: O st.data_editor suporta estilos de forma limitada, mas vamos tentar manter sua lógica
    try:
        df_styled = st.session_state["estoque"].style.map(estilo_saldo, subset=["Saldo"])
    except:
        df_styled = st.session_state["estoque"] # Se der erro no estilo, mostra normal

    # 3. Editor de Dados
    ed = st.data_editor(
        df_styled, 
        use_container_width=True, 
        num_rows="dynamic",
        key="editor_estoque_v2", # Mudei a key para forçar atualização visual
        column_config={
            "Saldo": st.column_config.NumberColumn(
                "✅ SALDO (KG)",  # Mudei emoji para Check Verde
                help="Quantidade em estoque (KG)",
                format="%.2f",
                step=1,
            ),
             "Preco_Base": st.column_config.NumberColumn(
                "💰 Preço Base",
                format="R$ %.2f"
            )
        }
    )
    
    # Salvar se houver alteração
    # Compara ignorando indices/estilos para garantir que salvamos os DADOS
    if not ed.equals(st.session_state["estoque"]):
        st.session_state["estoque"] = ed
        salvar_dados()
        # st.rerun() # Opcional: tire o comentário se precisar forçar atualização imediata
