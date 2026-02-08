elif menu == "📦 Estoque":
    st.title("📦 Estoque")
    
    # 1. Garante que o Saldo é número para a formatação funcionar
    st.session_state["estoque"]["Saldo"] = pd.to_numeric(st.session_state["estoque"]["Saldo"], errors='coerce').fillna(0)

    # 2. Estilização: Fundo AMARELO VIBRANTE e Texto VERDE ESCURO
    # Usamos map/applymap para garantir que pegue linha por linha
    def estilo_saldo(val):
        return 'background-color: #fff59d; color: #1b5e20; font-weight: 900; border: 1px solid #f9a825'

    # Aplica o estilo apenas na coluna Saldo
    df_styled = st.session_state["estoque"].style.map(estilo_saldo, subset=["Saldo"])
    
    # 3. Editor de Dados
    ed = st.data_editor(
        df_styled, 
        use_container_width=True, 
        num_rows="dynamic",
        column_config={
            "Saldo": st.column_config.NumberColumn(
                "⭐ SALDO (KG) ⭐",  # Destaque no TÍTULO da coluna com emojis
                help="Quantidade em estoque (KG)",
                format="%.2f",
                step=1,
            ),
             "Preco_Base": st.column_config.NumberColumn(
                "Preço Base",
                format="R$ %.2f"
            )
        }
    )
    
    # Salvar se houver alteração
    if not ed.equals(st.session_state["estoque"]):
        st.session_state["estoque"] = ed
        salvar_dados()
