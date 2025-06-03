import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import json
from datetime import datetime, date
import numpy as np

# Configurações da página
st.set_page_config(
    page_title="Air Quality Monitor",
    page_icon="🌬️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configurações da API
API_BASE_URL = "http://api:5000/api"

def get_api_data(endpoint):
    """Fazer requisição para a API"""
    try:
        response = requests.get(f"{API_BASE_URL}/{endpoint}", timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        st.error(f"Erro ao conectar com a API: {e}")
        return None

def clean_and_convert_dates(df):
    """Limpar e converter datas com múltiplas estratégias"""
    if df.empty:
        return df
    
    try:
        st.write(f"🔍 **Debug**: Processando {len(df)} registros...")
        
        # Mostrar algumas amostras de datas para debug
        if len(df) > 0:
            sample_dates = df[['date', 'time']].head(3)
            st.write("📝 **Amostra de datas:**")
            st.dataframe(sample_dates)
        
        # Estratégia 1: Tentar formato padrão
        df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], errors='coerce')
        
        # Estratégia 2: Se muitos NaT, tentar formato brasileiro
        nat_count = df['datetime'].isna().sum()
        if nat_count > len(df) * 0.5:  # Se mais de 50% são NaT
            st.warning(f"⚠️ {nat_count} datas inválidas no formato padrão, tentando formato brasileiro...")
            df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], 
                                          format='%d/%m/%Y %H.%M.%S', errors='coerce')
        
        # Estratégia 3: Tentar outros formatos comuns
        nat_count_after = df['datetime'].isna().sum()
        if nat_count_after > len(df) * 0.5:
            st.warning(f"⚠️ Ainda {nat_count_after} datas inválidas, tentando mais formatos...")
            # Tentar com diferentes separadores
            for fmt in ['%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%d-%m-%Y %H:%M:%S']:
                mask = df['datetime'].isna()
                if mask.any():
                    df.loc[mask, 'datetime'] = pd.to_datetime(
                        df.loc[mask, 'date'] + ' ' + df.loc[mask, 'time'], 
                        format=fmt, errors='coerce'
                    )
        
        # Contar quantos dados válidos temos
        valid_count = df['datetime'].notna().sum()
        invalid_count = df['datetime'].isna().sum()
        
        st.write(f"✅ **Resultado da conversão:**")
        st.write(f"   - Datas válidas: {valid_count}")
        st.write(f"   - Datas inválidas: {invalid_count}")
        
        # Se temos pelo menos alguns dados válidos, continuar
        if valid_count > 0:
            # Remover apenas registros com datetime inválido
            df_clean = df.dropna(subset=['datetime']).copy()
            df_clean = df_clean.sort_values('datetime', ascending=True)
            
            st.success(f"🎉 **{len(df_clean)} registros válidos** prontos para análise!")
            return df_clean
        else:
            st.error("❌ Nenhuma data válida encontrada em nenhum formato")
            return pd.DataFrame()
        
    except Exception as e:
        st.error(f"Erro ao processar datas: {e}")
        st.write("🔧 **Fallback**: Usando dados sem filtro de data...")
        # Retornar dados originais sem datetime para pelo menos mostrar algo
        return df

def filter_data_by_period(df, start_date, end_date):
    """Filtrar dados por período"""
    if df.empty or 'datetime' not in df.columns:
        return df
    
    try:
        mask = (df['datetime'].dt.date >= start_date) & (df['datetime'].dt.date <= end_date)
        return df[mask].copy()
    except Exception as e:
        st.error(f"Erro ao filtrar dados: {e}")
        return df

def main():
    """Função principal do dashboard"""
    
    # Título principal
    st.title("🌬️ Air Quality Real-Time Monitor - Dataset Completo")
    st.markdown("---")
    
    # Sidebar para controles
    st.sidebar.title("⚙️ Controles")
    
    # Auto-refresh
    auto_refresh = st.sidebar.checkbox("Auto Refresh (30s)", value=False)
    
    if st.sidebar.button("🔄 Atualizar Agora"):
        st.rerun()
    
    # Mostrar estatísticas gerais primeiro
    st.subheader("📊 Estatísticas do Sistema")
    
    stats = get_api_data("stats")
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Cache Records", stats.get('cache_records', 0))
        with col2:
            st.metric("Historical Files", stats.get('historical_files', 0))
        with col3:
            st.metric("Pending Alerts", stats.get('pending_alerts', 0))
        with col4:
            st.metric("System Status", "🟢 Online" if stats else "🔴 Offline")
    
    st.markdown("---")
    
    # Carregar dados
    with st.spinner("📡 Carregando dados da API..."):
        cache_data = get_api_data("cache")
    
    if cache_data and cache_data.get('data'):
        try:
            df_cache = pd.DataFrame(cache_data['data'])
            st.success(f"✅ **{len(df_cache)} registros** carregados da API")
            
            # Converter colunas numéricas
            numeric_cols = ['CO', 'NO2', 'Temperature', 'Relative_Humidity', 'Absolute_Humidity']
            for col in numeric_cols:
                if col in df_cache.columns:
                    df_cache[col] = pd.to_numeric(df_cache[col], errors='coerce')
            
            # Limpar e converter datas
            with st.expander("🔧 Debug: Processamento de Datas", expanded=False):
                df_cache = clean_and_convert_dates(df_cache)
            
            if df_cache.empty:
                st.error("❌ Nenhum dado válido após processamento")
                # Mostrar dados brutos pelo menos
                st.subheader("📋 Dados Brutos (sem filtro de data)")
                raw_df = pd.DataFrame(cache_data['data'])
                display_df = raw_df.drop(columns=['cache_key', 'timestamp'], errors='ignore').head(50)
                st.dataframe(display_df, use_container_width=True)
                return
            
            # Se temos datetime válido, mostrar controles de período
            if 'datetime' in df_cache.columns and df_cache['datetime'].notna().any():
                # Obter datas mín/máx válidas
                min_date = df_cache['datetime'].min().date()
                max_date = df_cache['datetime'].max().date()
                
                # Filtros de período na sidebar
                st.sidebar.markdown("---")
                st.sidebar.subheader("📅 Filtro de Período")
                
                st.sidebar.write(f"**Dados disponíveis:**")
                st.sidebar.write(f"📅 De: {min_date}")
                st.sidebar.write(f"📅 Até: {max_date}")
                
                # Seletores de data
                col1, col2 = st.sidebar.columns(2)
                with col1:
                    start_date = st.date_input(
                        "Data Inicial", 
                        value=min_date, 
                        min_value=min_date, 
                        max_value=max_date
                    )
                with col2:
                    end_date = st.date_input(
                        "Data Final", 
                        value=max_date, 
                        min_value=min_date, 
                        max_value=max_date
                    )
                
                # Filtrar dados pelo período
                df_filtered = filter_data_by_period(df_cache, start_date, end_date)
            else:
                # Usar todos os dados sem filtro
                df_filtered = df_cache
                start_date = "N/A"
                end_date = "N/A"
            
            # Opções de visualização
            st.sidebar.markdown("---")
            st.sidebar.subheader("📊 Opções de Visualização")
            show_all_data = st.sidebar.checkbox("Mostrar todos os registros na tabela", value=False)
            max_graph_points = st.sidebar.slider("Pontos máximos nos gráficos", 50, 1000, 200)
            
        except Exception as e:
            st.error(f"Erro ao processar dados: {e}")
            df_filtered = pd.DataFrame()
            start_date = "Erro"
            end_date = "Erro"
    else:
        df_filtered = pd.DataFrame()
        start_date = "N/A"
        end_date = "N/A"
    
    # Seção de dados
    if not df_filtered.empty:
        total_records = len(df_cache) if 'df_cache' in locals() else len(df_filtered)
        filtered_records = len(df_filtered)
        
        st.subheader(f"⚡ Dados Processados ({start_date} até {end_date})")
        
        # Informações do período
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Carregado", f"{total_records:,}")
        with col2:
            st.metric("Registros Válidos", f"{filtered_records:,}")
        with col3:
            percentage = (filtered_records / total_records * 100) if total_records > 0 else 0
            st.metric("% Válido", f"{percentage:.1f}%")
        with col4:
            if isinstance(start_date, date) and isinstance(end_date, date):
                days = (end_date - start_date).days + 1
                st.metric("Dias", days)
            else:
                st.metric("Status", "Sem filtro de data")
        
        # Tabela de dados
        st.subheader("📋 Dados Tabulares")
        
        if show_all_data:
            st.write(f"**Mostrando todos os {filtered_records} registros:**")
            display_df = df_filtered.drop(columns=['cache_key', 'datetime', 'timestamp'], errors='ignore')
            st.dataframe(display_df, use_container_width=True, height=400)
        else:
            st.write(f"**Mostrando últimos 50 de {filtered_records} registros:**")
            display_df = df_filtered.tail(50).drop(columns=['cache_key', 'datetime', 'timestamp'], errors='ignore')
            st.dataframe(display_df, use_container_width=True)
        
        # Gráficos simples (mesmo sem datetime)
        if len(df_filtered) > 1:
            # Preparar dados para gráfico
            if len(df_filtered) > max_graph_points:
                step = len(df_filtered) // max_graph_points
                plot_data = df_filtered.iloc[::step].copy()
                st.info(f"📊 Mostrando {len(plot_data)} pontos de {len(df_filtered)} disponíveis")
            else:
                plot_data = df_filtered.copy()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("�� Monóxido de Carbono (CO)")
                if 'datetime' in plot_data.columns:
                    fig_co = px.line(plot_data, x='datetime', y='CO', title="Níveis de CO")
                else:
                    fig_co = px.line(plot_data.reset_index(), x='index', y='CO', title="Níveis de CO (por registro)")
                fig_co.add_hline(y=10, line_dash="dash", line_color="red", annotation_text="Crítico (10)")
                st.plotly_chart(fig_co, use_container_width=True)
            
            with col2:
                st.subheader("🟦 Dióxido de Nitrogênio (NO2)")
                if 'datetime' in plot_data.columns:
                    fig_no2 = px.line(plot_data, x='datetime', y='NO2', title="Níveis de NO2")
                else:
                    fig_no2 = px.line(plot_data.reset_index(), x='index', y='NO2', title="Níveis de NO2 (por registro)")
                fig_no2.add_hline(y=200, line_dash="dash", line_color="red", annotation_text="Crítico (200)")
                st.plotly_chart(fig_no2, use_container_width=True)
            
            # Estatísticas
            st.subheader("📈 Estatísticas dos Dados")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                co_stats = df_filtered['CO'].describe()
                st.metric("CO Médio", f"{co_stats['mean']:.2f}")
                st.caption(f"Min: {co_stats['min']:.2f} | Max: {co_stats['max']:.2f}")
                critical_co = len(df_filtered[df_filtered['CO'] > 10])
                st.caption(f"🚨 Críticos: {critical_co}")
            
            with col2:
                no2_stats = df_filtered['NO2'].describe()
                st.metric("NO2 Médio", f"{no2_stats['mean']:.2f}")
                st.caption(f"Min: {no2_stats['min']:.2f} | Max: {no2_stats['max']:.2f}")
                critical_no2 = len(df_filtered[df_filtered['NO2'] > 200])
                st.caption(f"🚨 Críticos: {critical_no2}")
            
            with col3:
                temp_stats = df_filtered['Temperature'].describe()
                st.metric("Temp Média", f"{temp_stats['mean']:.1f}°C")
                st.caption(f"Min: {temp_stats['min']:.1f}°C | Max: {temp_stats['max']:.1f}°C")
            
            with col4:
                humidity_stats = df_filtered['Relative_Humidity'].describe()
                st.metric("Umidade Média", f"{humidity_stats['mean']:.1f}%")
                st.caption(f"Min: {humidity_stats['min']:.1f}% | Max: {humidity_stats['max']:.1f}%")
        
    else:
        st.warning("❌ Dados não disponíveis")
        st.info("🔄 Tente atualizar a página ou verificar a conexão com a API")
    
    st.markdown("---")
    
    # Seção de alertas
    st.subheader("🚨 Alertas Críticos")
    alerts_data = get_api_data("alerts")
    if alerts_data and alerts_data.get('alerts'):
        for alert in alerts_data['alerts']:
            st.error(f"⚠️ {alert.get('message', 'Alerta crítico')}")
    else:
        st.success("✅ Nenhum alerta crítico")
    
    # Auto-refresh
    if auto_refresh:
        time.sleep(30)
        st.rerun()

if __name__ == "__main__":
    main()
