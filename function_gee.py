import streamlit as st
import streamlit_folium
from streamlit_folium import st_folium
import geemap
import geemap.foliumap as geemap
import ee
import plotly.express as px
import folium
import pandas as pd
import geopandas as gpd
from datetime import datetime
import json
import os
import pathlib
import tempfile
from zipfile import ZipFile
import fiona
from shapely.geometry import LineString, Polygon, MultiPolygon
import io


##Corrija o arquivo removendo Z
def convert_3D_2D(geometry):
    """
    Converte uma geometria 3D em 2D.
    """
    if geometry.has_z:
        if geometry.geom_type == 'Polygon':
            # Constrói um novo Polygon sem a coordenada Z
            return Polygon([(x, y) for x, y, z in geometry.exterior.coords])
        elif geometry.geom_type == 'MultiPolygon':
            # Constrói um novo MultiPolygon sem as coordenadas Z
            new_polygons = []
            for polygon in geometry.geoms:
                new_polygons.append(Polygon([(x, y) for x, y, z in polygon.exterior.coords]))
            return MultiPolygon(new_polygons)
    return geometry

def convert_to_geojson(uploaded_file):
    file_extension = os.path.splitext(uploaded_file.name)[1].lower()
    gdf_list = []

    # Configura suporte para leitura de arquivos KML e KMZ
    fiona.drvsupport.supported_drivers['KML'] = 'rw'
    fiona.drvsupport.supported_drivers['libkml'] = 'rw'
    fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'

    # Para arquivos KMZ, ainda precisaremos extrair os arquivos internos
    if file_extension == '.kmz':
        with tempfile.TemporaryDirectory() as extraction_dir:
            with ZipFile(io.BytesIO(uploaded_file.getvalue()), 'r') as kmz:
                kmz.extractall(extraction_dir)
            for filename in os.listdir(extraction_dir):
                if filename.lower().endswith('.kml'):
                    kml_file_path = os.path.join(extraction_dir, filename)
                    for layer in fiona.listlayers(kml_file_path):
                        gdf = gpd.read_file(kml_file_path, layer=layer, driver='LIBKML')
                        gdf_list.append(gdf)

    # Para arquivos KML, SHP, GPKG diretamente
    elif file_extension in ['.kml', '.shp', '.gpkg']:
        gdf = gpd.read_file(io.BytesIO(uploaded_file.getvalue()))
        gdf_list.append(gdf)

    # Para arquivos GeoJSON diretamente
    elif file_extension == '.geojson':
        gdf = gpd.read_file(io.BytesIO(uploaded_file.getvalue()))
        gdf_list = [gdf]

    # Combina todos os GeoDataFrames em um único DataFrame
    if gdf_list:
        combined_gdf = gpd.GeoDataFrame(pd.concat(gdf_list, ignore_index=True),crs="EPSG:4326")
    # Convertendo o GeoDataFrame para GeoJSON
        combined_gdf['geometry']=combined_gdf['geometry'].apply(convert_3D_2D)
               
    else:
        combined_gdf = None
        print("No geographical data found.")

    # Exibe o GDF para verificação
    if combined_gdf is not None:
        st.write('Arquivo Carregado com sucesso')
    else:
        st.write("No valid geographical data loaded.")

    return combined_gdf


# Função de nuvens, fator de escala e clip
def maskCloudAndShadowsSR(image, roi):
    cloudProb = image.select('MSK_CLDPRB')
    snowProb = image.select('MSK_SNWPRB')
    cloud = cloudProb.lt(5)
    snow = snowProb.lt(5)
    scl = image.select('SCL')
    shadow = scl.eq(3)  # 3 = cloud shadow
    cirrus = scl.eq(10)  # 10 = cirrus
    # Probabilidade de nuvem inferior a 5% ou classificação de sombra de nuvem
    mask = (cloud.And(snow)).And(cirrus.neq(1)).And(shadow.neq(1))
    return image.updateMask(mask).divide(10000)\
        .select("B.*")\
        .clipToCollection(roi)\
        .copyProperties(image, image.propertyNames())
# Cálculo do índice

def indice(image):
    ndvi = image.normalizedDifference(['B8','B4']).rename('ndvi')
    ndre = image.normalizedDifference(['B8','B5']).rename('ndre') 
    evi = image.expression('2.5 * ((N - R) / (N + (6 * R) - (7.5 * B) + 1))',
        { #//Huete 2002
    'N': image.select('B8'), 
    'R': image.select('B4'), 
    'B': image.select('B2')}).rename('evi') 
    # mndwi = image.normalizedDifference(['B3','B11']).rename('mndwi')
    ndwi = image.normalizedDifference(['B3','B8']).rename('ndwi')
    ndmi = image.normalizedDifference(['B8','B11']).rename('ndmi')
    # ndpi = image.normalizedDifference(['B11','B3']).rename('ndpi')
    # spri = image.normalizedDifference(['B2','B3']).rename('spri')
    #   AWEInsh (Automated Water Extraction Index - Normalized, Shadow-Removed): 
    # aweinsh = image.expression(
    #         '(4 * (GREEN - SWIR) - (0.25 * NIR + 2.75 * SWIR))',
    #         {
    #             'GREEN': image.select('B3'), # Verde
    #             'NIR': image.select('B8'), # Infravermelho próximo
    #             'SWIR': image.select('B11'), # Infravermelho de onda curta
    #         }
    #     ).rename('aweinsh')
    
    savi = image.expression(
            '((NIR - RED) / (NIR + RED + L)) * (1 + L)',
            {
                'NIR': image.select('B8'), # Infravermelho próximo
                'RED': image.select('B4'), # Vermelho
                'L': 0.5 # Fator de ajuste do solo (0.5 para vegetação)
            }
        ).rename('savi')
    
    return image.addBands([ndvi, ndre,evi,ndwi,ndmi,savi]).set({'data': image.date().format('yyyy-MM-dd')})

# Função para aplicar a redução por regiões para toda a coleção usando map
def reduce_region_for_collection(img, roi):
    # Obtém a data da imagem
    date = img.date().format('yyyy-MM-dd')

    # Aplica a redução por regiões para a imagem
    stats = img.reduceRegions(
        collection=roi,
        reducer=ee.Reducer.mean(),
        scale=10  # Defina a escala apropriada para sua aplicação
    )

    # Adiciona a data à propriedade 'data'
    stats = stats.map(lambda f: f.set('data', date))

    return stats
