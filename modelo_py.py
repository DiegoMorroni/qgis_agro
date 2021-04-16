#mode

from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsProcessingParameterRasterDestination
from qgis.core import QgsProcessingParameterDefinition
from qgis.core import QgsCoordinateReferenceSystem
import processing


class Processo(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        param = QgsProcessingParameterRasterLayer('BANDANIR', 'BANDA_NIR', defaultValue=None)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        self.addParameter(QgsProcessingParameterRasterLayer('BANDARED', 'BANDA_RED', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('fazenda', 'fazenda', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('Fazenda_centroideis', 'fazenda_centroideis', type=QgsProcessing.TypeVectorPoint, createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('Fazenda', 'fazenda', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Fazenda_reclass', 'fazenda_reclass', createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('Carreadores', 'carreadores', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(9, model_feedback)
        results = {}
        outputs = {}

        # Raster calculator
        alg_params = {
            'CELLSIZE': 0,
            'CRS': 'ProjectCrs',
            'EXPRESSION': ' ( \"BANDA_NIR@1\" - \"BANDA_RED@1\"  ) /  ( \"BANDA_NIR@1\" + \"BANDA_RED@1\" ) ',
            'EXTENT': None,
            'LAYERS': [parameters['BANDANIR'],parameters['BANDARED']],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['RasterCalculator'] = processing.run('qgis:rastercalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Corrigir geometrias
        alg_params = {
            'INPUT': parameters['fazenda'],
            'OUTPUT': parameters['Fazenda']
        }
        outputs['CorrigirGeometrias'] = processing.run('native:fixgeometries', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Fazenda'] = outputs['CorrigirGeometrias']['OUTPUT']

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Recortar raster pela camada de máscara
        alg_params = {
            'ALPHA_BAND': False,
            'CROP_TO_CUTLINE': True,
            'DATA_TYPE': 0,
            'EXTRA': '',
            'INPUT': outputs['RasterCalculator']['OUTPUT'],
            'KEEP_RESOLUTION': False,
            'MASK': outputs['CorrigirGeometrias']['OUTPUT'],
            'MULTITHREADING': False,
            'NODATA': None,
            'OPTIONS': '',
            'SET_RESOLUTION': False,
            'SOURCE_CRS': None,
            'TARGET_CRS': None,
            'X_RESOLUTION': None,
            'Y_RESOLUTION': None,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['RecortarRasterPelaCamadaDeMscara'] = processing.run('gdal:cliprasterbymasklayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Reclassificar por tabela
        alg_params = {
            'DATA_TYPE': 5,
            'INPUT_RASTER': outputs['RecortarRasterPelaCamadaDeMscara']['OUTPUT'],
            'NODATA_FOR_MISSING': False,
            'NO_DATA': -9999,
            'RANGE_BOUNDARIES': 0,
            'RASTER_BAND': 1,
            'TABLE': [-1,0.099,0,0.099,0.14, 5, 0.14,0.18,22,0.18,0.23,58, 0.23,0.7,98, 0.7,1,135],
            'OUTPUT': parameters['Fazenda_reclass']
        }
        outputs['ReclassificarPorTabela'] = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Fazenda_reclass'] = outputs['ReclassificarPorTabela']['OUTPUT']

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Estatísticas Zonais
        alg_params = {
            'COLUMN_PREFIX': 'TCH_',
            'INPUT_RASTER': outputs['ReclassificarPorTabela']['OUTPUT'],
            'INPUT_VECTOR': outputs['CorrigirGeometrias']['OUTPUT'],
            'RASTER_BAND': 1,
            'STATS': [2,3,4,5,6]
        }
        outputs['EstatsticasZonais'] = processing.run('qgis:zonalstatistics', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # Reprojetar camada
        alg_params = {
            'INPUT': outputs['EstatsticasZonais']['INPUT_VECTOR'],
            'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:32722'),
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ReprojetarCamada'] = processing.run('native:reprojectlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Centroides
        alg_params = {
            'ALL_PARTS': True,
            'INPUT': outputs['EstatsticasZonais']['INPUT_VECTOR'],
            'OUTPUT': parameters['Fazenda_centroideis']
        }
        outputs['Centroides'] = processing.run('native:centroids', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Fazenda_centroideis'] = outputs['Centroides']['OUTPUT']

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        # Buffer
        alg_params = {
            'DISSOLVE': False,
            'DISTANCE': 10,
            'END_CAP_STYLE': 0,
            'INPUT': outputs['ReprojetarCamada']['OUTPUT'],
            'JOIN_STYLE': 0,
            'MITER_LIMIT': 2,
            'SEGMENTS': 5,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Buffer'] = processing.run('native:buffer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        # Diferença simétrica
        alg_params = {
            'INPUT': outputs['Buffer']['OUTPUT'],
            'OVERLAY': outputs['ReprojetarCamada']['OUTPUT'],
            'OVERLAY_FIELDS_PREFIX': '',
            'OUTPUT': parameters['Carreadores']
        }
        outputs['DiferenaSimtrica'] = processing.run('native:symmetricaldifference', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Carreadores'] = outputs['DiferenaSimtrica']['OUTPUT']
        return results

    def name(self):
        return 'processo'

    def displayName(self):
        return 'processo'

    def group(self):
        return 'usa'

    def groupId(self):
        return 'usa'

    def createInstance(self):
        return Processo()
