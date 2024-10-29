###Monitoramento de Lavoura 
import streamlit as st
import geemap.foliumap as geemap
import ee
import plotly.express as px
import pandas as pd
import geopandas as gpd
import json
import os
from datetime import datetime
import altair as alt

##Funções do código functio_gee
from function_gee import convert_to_geojson
from function_gee import indice
from function_gee import maskCloudAndShadowsSR
from function_gee import reduce_region_for_collection


# Configuração da página
st.set_page_config(layout="wide")
st.sidebar.image('assets/Logo.png')
# st.sidebar.markdown('Desenvolvido por [Christhian Cunha](https://www.linkedin.com/in/christhian-santana-cunha/)')
st.sidebar.markdown('Conheça nossas formações [AmbGEO](https://ambgeo.com/)')

st.title('🌿 Visualização e Análise de Índices Espectrais com Imagens Sentinel-2')

st.markdown("""
#### Este aplicativo permite o processamento, visualização e download de imagens do satélite Sentinel-2 diretamente do Google Earth Engine. 

Com esta ferramenta, o usuário pode:
- Carregar uma região de interesse (ROI) em formato GeoJSON, KML, SHP ou GPKG.
- Definir o período desejado para análise.
- Selecionar e visualizar índices espectrais como NDVI, EVI, NDWI, entre outros.
- Inspecionar e visualizar imagens disponíveis para as datas selecionadas.
- Baixar as imagens processadas em formatos de fácil manipulação (GeoTIFF), inclusive em tiles para facilitar o download de grandes volumes de dados.

A aplicação é voltada para análises geoespaciais que utilizam dados de sensoriamento remoto, permitindo a exploração visual de informações sobre vegetação, água e outros componentes da superfície terrestre.
""")
# Inicializar o mapa com ROI como None


##Login gee
m = geemap.Map()

##Criar uma função 


###Definição da áre de estudo 
roi = None

# Upload do arquivo GeoJSON
st.sidebar.subheader("Carregue um arquivo conforme os formatos indicados:")
##Trabalhando com a roi como dado de entrada
uploaded_file = st.sidebar.file_uploader("Faça o upload da sua área de estudo", type=["geojson",'kml','kmz','gkpg'])
st.sidebar.markdown("""### Para criar o arquivo **GeoJSON** use o site [geojson.io](https://geojson.io/#new&map=2/0/20).""")

# Supondo que convert_to_geojson retorna um GeoDataFrame
if uploaded_file is not None:
    gdf = convert_to_geojson(uploaded_file)

    # Verifique se a coluna 'Name' está presente
    if 'Name' not in gdf.columns:
        gdf['Name'] = 'Área de interesse'

    # Remover duplicatas baseadas na coluna 'Name'
    gdf = gdf.drop_duplicates(subset='Name')

    # Converter de GeoDataFrame para JSON
    shp_json = gdf.to_json()
    f_json = json.loads(shp_json)['features']

    # Carrega a FeatureCollection no Earth Engine
    roi = ee.FeatureCollection(f_json)
    st.sidebar.write("Arquivo carregado com sucesso!")
else:
    st.sidebar.error("Por favor, carregue uma área de estudo válida.")

# Ponto central para o mapa
point = ee.Geometry.Point(-45.259679, -17.871838)
m.centerObject(point, 8)
m.setOptions("HYBRID")

# Adicionar campos de datas iniciais e finais na barra lateral
start_date = st.sidebar.date_input("📅Selecione a data inicial", datetime(2023, 1, 1))
end_date = st.sidebar.date_input("📅Selecione a data final", datetime.now())
# Adicionar slider para definir o limite de nuvens
cloud_percentage_limit = st.sidebar.slider("Limite de percentual de nuvens", 0, 100, 5)


# Adiciona a ROI se ela existir
if roi is not None:      
    # Coleção de imagens 
    collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")\
                    .filterBounds(roi)\
                    .filter(ee.Filter.date(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))\
                    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloud_percentage_limit))\
                    .map(lambda image: maskCloudAndShadowsSR(image, roi))\
                    .map(indice)

    # Criar a tabela usando os dados da coleção filtrada
    data_table = pd.DataFrame({
        "Data": collection.aggregate_array("data").getInfo(),
        "Percentual de Nuvens": collection.aggregate_array("CLOUDY_PIXEL_PERCENTAGE").getInfo(),
        "ID": collection.aggregate_array("system:id").getInfo()
    })
    
    # Criar checkboxes para escolher os índices
    st.sidebar.subheader("✅Escolha os índices para visualização e análise estatística:")
    show_ndvi = st.sidebar.checkbox("🌳NDVI", value=True)
    show_ndre = st.sidebar.checkbox("🌱NDRE", value=False)
    show_evi = st.sidebar.checkbox("🌳EVI", value=True)
    show_ndwi = st.sidebar.checkbox("💧NDWI", value=False)
    show_ndmi = st.sidebar.checkbox("🌱NDMI", value=False)
    show_spri = st.sidebar.checkbox("🌱SPRI", value=False)
    show_savi = st.sidebar.checkbox("🌱SAVI", value=False)
 
 
    # Monta a lista 'bands' de acordo com as seleções dos checkboxes
    bands = []
    if show_ndvi: bands.append('ndvi')
    if show_ndre: bands.append('ndre')
    if show_evi: bands.append('evi')
    if show_ndwi: bands.append('ndwi')
    if show_ndmi: bands.append('ndmi')
    if show_spri: bands.append('spri')
    if show_savi: bands.append('savi')


    # Verificar se 'bands' está definido corretamente
    if bands:
           
        # Aqui você coloca sua lógica de seleção da coleção
        stats_collection = collection.select(bands).map(lambda image: reduce_region_for_collection(image, roi))

        # Converte para df
        df = geemap.ee_to_df(stats_collection.flatten())
        
        # Adiciona a data como coluna no formato datetime
        df['datetime'] = pd.to_datetime(df['data'], format='%Y-%m-%d')

        # Renomear colunas para os nomes dos índices selecionados
        if len(bands) == 1:
            df.rename(columns={'mean': bands[0]}, inplace=True)
        else:
            rename_dict = {f'mean_{i+1}': bands[i] for i in range(len(bands)) if f'mean_{i+1}' in df.columns}
            df.rename(columns=rename_dict, inplace=True)

        # Agora, o DataFrame já está com as colunas renomeadas corretamente
        fig = px.line(df, x='datetime', y=bands, title='Série Temporal de Índices', 
                        labels={'value': 'Índice', 'variable': 'Tipo de Índice'})

        fig_bar = px.bar(df, x='datetime', y=bands, 
                            title='Gráfico de Barras de Índices',
                            labels={'value': 'Índice', 'variable': 'Tipo de Índice'},
                            barmode='group')
        
        ## Criando colunas 1 e 2 para organizar os gráficos e tabelas
        col1, col2 = st.columns([0.6, 0.4])
        with col1:
            tab1, tab2 = st.tabs(["📈 Gráfico de Linha", "📈 Imagens Disponíveis"])
            tab1.subheader('Gráfico')
            tab1.plotly_chart(fig, use_container_width=True)
            tab2.subheader("Tabela de Informações")
            tab2.write(data_table)

        with col2:
            st.subheader('DataFrame')
            st.dataframe(df.style.set_table_styles([{'selector': 'table', 'props': [('width', '400px')]}]))

        # Adicionar colunas de mês e ano para facilitar a agregação no heatmap
        df['month'] = df['datetime'].dt.month
        df['year'] = df['datetime'].dt.year

        # Se o usuário selecionou mais de um índice, ele precisa escolher qual ver no heatmap
        selected_index = st.selectbox("Selecione o índice para ver no Heatmap:", bands)

        # # Criar uma tabela pivot para preparar os dados do heatmap (média por mês e ano)
        # df_pivot = df.pivot_table(values=selected_index, index='year', columns='month', aggfunc='mean')

        # Filtrar os dados para o índice selecionado
        df_filtered = df[['year', 'month', selected_index]].dropna()
        # Criar o gráfico de heatmap usando Altair
        heatmap = alt.Chart(df_filtered).mark_rect().encode(
            x=alt.X('month:O', title='Mês'),
            y=alt.Y('year:O', title='Ano'),
            color=alt.Color(f'{selected_index}:Q', title=selected_index, scale=alt.Scale(scheme='yellowgreenblue')),
            tooltip=[alt.Tooltip('month:O', title='Mês'), alt.Tooltip('year:O', title='Ano'), alt.Tooltip(f'{selected_index}:Q', title=selected_index)]
        ).properties(
            title=f"Heatmap do Índice {selected_index} por Mês e Ano",
            width=600,
            height=300
        )

        # Exibir o heatmap no Streamlit
        st.altair_chart(heatmap, use_container_width=True)
        
        
        st.divider()

        # Criar uma imagem de contorno da FeatureCollection
        contour_image = ee.Image().byte().paint(featureCollection=roi, color=1, width=2)
        m.addLayer(contour_image, {'palette': 'FF0000'}, 'Região de Interesse')

       # Função para exportar a imagem para um arquivo GeoTIFF
        def export_image(image, date):
            try:
                # Tentativa de exportar a imagem inteira
                url = image.select().getDownloadURL({
                    'name': f'image{date}',                # Nome do arquivo
                    'scale': 20,                           # Define a escala
                    'crs': 'EPSG:4674',                    # Sistema de referência
                    'region': roi.geometry(),              # Define a região da ROI
                    'format': 'GEO_TIFF'                   # Formato de exportação
                })
                st.sidebar.success(f"Imagem exportada de {date} com sucesso. Baixe [aqui]({url}).")
            except Exception as e:
                # Se o erro for devido ao limite de tamanho, dividir em tiles
                if 'Total request size' in str(e):
                    st.sidebar.error(f"Erro ao exportar a imagem: {str(e)}. Exportando por tiles menores.")
                    export_image_by_tiles(image, date)
                else:
                    st.sidebar.error(f"Erro ao exportar a imagem: {str(e)}")

        # Função para exportar a imagem dividida em tiles menores
        def export_image_by_tiles(image, date, tile_size=0.05):
            """Exportar imagem dividida em tiles menores para evitar exceder o limite de 50MB."""
            # Calcular o tamanho do tile em função do tamanho máximo de 50 MB
            grid = geemap.fishnet(roi, rows=5, cols=5)  # Gera uma grade para dividir a imagem
            for idx, feature in enumerate(grid.getInfo()['features']):
                tile_geometry = ee.Feature(feature).geometry()
                try:
                    # Exportar cada tile individualmente
                    url = image.getDownloadURL({
                        'name': f'image_{date}_tile_{idx+1}',  # Nome do tile
                        'scale': 20,                           # Define a escala
                        'crs': 'EPSG:4674',                    # Sistema de referência
                        'region': tile_geometry,               # Define a região do tile
                        'format': 'GEO_TIFF'                   # Formato de exportação
                    })
                    st.sidebar.success(f"Tile {idx+1} exportado com sucesso. Baixe [aqui]({url}).")
                except Exception as e:
                    st.sidebar.error(f"Erro ao exportar o tile {idx+1}: {str(e)}")

        # Criar lista de botões para cada data
        selected_dates = st.sidebar.multiselect("✅Selecione as datas", data_table["Data"].tolist())

        # Verificar se há datas selecionadas
        if not selected_dates:
            # Se não houver datas selecionadas, selecionar a última imagem automaticamente
            selected_collection = collection.sort('data', False).first()
            m.addLayer(selected_collection, {'bands': ['B12', 'B8', 'B4'], 'min': 0.1, 'max': 0.4}, 'Img Atual - False Color')
            m.addLayer(selected_collection, {'bands': ['B4', 'B3', 'B2'], 'min': 0.01, 'max': 0.2}, 'Img Atual - RGB')
        else:
            selected_collection = collection.filter(ee.Filter.inList('data', selected_dates))

            if len(selected_dates) > 1:
                for date in selected_dates:
                    m.addLayer(selected_collection.filter(ee.Filter.eq('data', date)), 
                            {'bands': ['B12', 'B8', 'B4'], 'min': 0.1, 'max': 0.4}, 
                            f'Img False Color {date}')
                    m.addLayer(selected_collection.filter(ee.Filter.eq('data', date)), 
                            {'bands': ['B4', 'B3', 'B2'], 'min': 0.01, 'max': 0.2}, 
                            f'Img RGB {date}')
            else:
                date = selected_dates[0]
                m.addLayer(selected_collection, {'bands': ['B12', 'B8', 'B4'], 'min': 0.1, 'max': 0.4}, f'Img False Color {date}')
                m.addLayer(selected_collection, {'bands': ['B4', 'B3', 'B2'], 'min': 0.01, 'max': 0.2}, f'Img RGB {date}')

        m.centerObject(roi, 13)

        # Função para adicionar camadas de acordo com os índices escolhidos
        def add_index_layer(index, vis_params, label):
            if not selected_dates:
                m.addLayer(selected_collection.select(index), vis_params, f'{label} - Última Imagem')
            else:
                if len(selected_dates) > 1:
                    for date in selected_dates:
                        filtered_collection = selected_collection.filter(ee.Filter.eq('data', date))
                        m.addLayer(filtered_collection.select(index), vis_params, f'{label} {date}')
                else:
                    m.addLayer(selected_collection.select(index), vis_params, f'{label} {selected_dates[0]}')

        # Adicionar os índices selecionados ao mapa
        if show_ndwi:
            add_index_layer('ndwi', {'min': -0.5, 'max': 0.25, 'palette': ['cyan', 'lightblue', 'blue']}, 'NDWI')
        if show_ndmi:
            add_index_layer('ndmi', {'min': -1, 'max': 1, 'palette': ['cyan', 'lightblue', 'blue']}, 'NDMI')
        if show_spri:
            add_index_layer('spri', {'min': -1, 'max': 0.1, 'palette': ['red', 'yellow', 'green']}, 'SPRI')
        if show_savi:
            add_index_layer('savi', {'min': 0, 'max': 1, 'palette': ['red', 'yellow', 'green']}, 'SAVI')
        if show_ndvi:
            add_index_layer('ndvi', {'min': 0, 'max': 1, 'palette': ['red', 'yellow', 'green']}, 'NDVI')
        if show_ndre:
            add_index_layer('ndre', {'min': 0, 'max': 1, 'palette': ['red', 'yellow', 'green']}, 'NDRE')
        if show_evi:
            add_index_layer('evi', {'min': 0, 'max': 1, 'palette': ['red', 'yellow', 'green']}, 'EVI')

        # Botão para acionar o download dos dados
        if st.sidebar.button("Download dos Dados"):
            if 'roi' in locals() and roi is not None:
                for date in selected_dates:
                    selected_collection_date = selected_collection.filter(ee.Filter.eq('data', date))
                    export_image(selected_collection_date.first(), date)
            else:
                st.warning("Por favor, selecione uma área de interesse antes de fazer o download.")

# Exibe o mapa no Streamlit
m.to_streamlit()

