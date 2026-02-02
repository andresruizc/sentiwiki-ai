"""
Sistema de filtrado inteligente por metadatos para Sentinel Missions (SentiWiki).
"""

import re
from typing import Dict, List, Optional, Set
from loguru import logger

from src.utils.metadata_extractor_sentiwiki import MetadataExtractor
from src.utils.metadata_normalizer_sentiwiki import MetadataNormalizer


class MetadataFilter:
    """Filtro inteligente de metadatos para mejorar la calidad del retrieval en Sentinel."""
    
    def __init__(self, enable_logging: bool = True):
        self.enable_logging = enable_logging
        self.metadata_extractor = MetadataExtractor(enable_logging=False)  # Reuse existing extractor
        
        # Patrones para detectar tipos de consulta
        self.procedure_patterns = [
            r'\b(?:procedure|procedimiento)s?\b',
            r'\b(?:process|proceso)s?\b',
            r'\b(?:step|paso)s?\b',
            r'\b(?:how to|c[oó]mo)\b',
            r'\b(?:implementation|implementaci[oó]n)\b',
            r'\b(?:workflow|flujo)\b',
        ]
        
        self.definition_patterns = [
            r'\b(?:what is|qu[eé] es)\b',
            r'\b(?:definition|definici[oó]n)\b',
            r'\b(?:meaning|significado)\b',
            r'\b(?:concept|concepto)\b',
            r'\b(?:explain|explicar)\b',
        ]
        
        self.specification_patterns = [
            r'\b(?:specification|especificaci[oó]n)\b',
            r'\b(?:requirement|requisito)s?\b',
            r'\b(?:parameter|par[aá]metro)s?\b',
            r'\b(?:characteristic|caracter[ií]stica)s?\b',
            r'\b(?:accuracy|precisi[oó]n)\b',
            r'\b(?:resolution|resoluci[oó]n)\b',
        ]
        
        # Patrones para detectar instrumentos Sentinel
        self.instrument_patterns = {
            'SAR': [r'\bsar\b', r'\bsynthetic\s*aperture\s*radar\b'],
            'OLCI': [r'\bolci\b', r'\bocean\s*and\s*land\s*colour\s*instrument\b'],
            'SLSTR': [r'\bslstr\b', r'\bsea\s*and\s*land\s*surface\s*temperature\s*radiator\b'],
            'MSI': [r'\bmsi\b', r'\bmultispectral\s*instrument\b'],
            'SRAL': [r'\bsral\b', r'\bsar\s*altimeter\b'],
            'MWR': [r'\bmwr\b', r'\bmicroWave\s*radiometer\b'],
            'TROPOMI': [r'\btropomi\b'],
            'OLCI': [r'\bolci\b'],
        }
        
        # Patrones para detectar productos Sentinel
        self.product_patterns = [
            r'\b(?:level\s*)?[lL](\d+)\b',  # L1, L2, L3, Level-1, etc.
            r'\bproduct\b',
            r'\bdata\s*product\b',
            r'\b(?:l1c|l2a|l3)\b',  # Formatos específicos
        ]
    
    def analyze_query(self, query: str) -> Dict[str, any]:
        """Analiza una consulta para extraer intención y metadatos relevantes para Sentinel."""
        query_lower = query.lower()
        
        # Extraer misión usando el extractor existente
        mission = self.metadata_extractor.extract_mission(query)
        missions = self.metadata_extractor.extract_missions(query)
        document_type = self.metadata_extractor.extract_document_type(query)
        
        # Detectar instrumentos mencionados
        instruments = self._extract_instruments(query)
        
        # Detectar productos mencionados
        products = self._extract_products(query)
        
        # Detectar tipo de consulta
        query_type = 'general'
        if any(re.search(pattern, query_lower) for pattern in self.procedure_patterns):
            query_type = 'procedure'
        elif any(re.search(pattern, query_lower) for pattern in self.definition_patterns):
            query_type = 'definition'
        elif any(re.search(pattern, query_lower) for pattern in self.specification_patterns):
            query_type = 'specification'
        
        analysis = {
            'query_type': query_type,
            'mission': mission,
            'missions': missions,
            'document_type': document_type,
            'instruments': instruments,
            'products': products,
            'filters': {}  # No hard filters, only boost
        }
        
        if self.enable_logging:
            logger.info(
                f"Query analysis: type={query_type} | "
                f"mission={mission} | instruments={instruments} | "
                f"document_type={document_type} | products={products}"
            )
        
        return analysis
    
    def _extract_instruments(self, query: str) -> List[str]:
        """Extrae instrumentos mencionados en la query."""
        query_lower = query.lower()
        found_instruments = []
        
        for instrument, patterns in self.instrument_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    if instrument not in found_instruments:
                        found_instruments.append(instrument)
                    break
        
        return found_instruments
    
    def _extract_products(self, query: str) -> List[str]:
        """Extrae productos mencionados en la query."""
        query_lower = query.lower()
        found_products = []
        
        # Buscar niveles de producto (L1, L2, L3, etc.)
        level_matches = re.findall(r'\b(?:level\s*)?[lL](\d+)\b', query_lower)
        for level in level_matches:
            product = f"L{level}"
            if product not in found_products:
                found_products.append(product)
        
        # Buscar formatos específicos
        if re.search(r'\bl1c\b', query_lower):
            if 'L1C' not in found_products:
                found_products.append('L1C')
        if re.search(r'\bl2a\b', query_lower):
            if 'L2A' not in found_products:
                found_products.append('L2A')
        if re.search(r'\bl3\b', query_lower):
            if 'L3' not in found_products:
                found_products.append('L3')
        
        return found_products
    
    def _generate_filters(self, analysis: Dict[str, any]) -> Dict[str, any]:
        """Genera filtros de Qdrant basados en el análisis de la consulta.
        
        NOTE: We use boost instead of hard filters for most metadata because
        hard filters can be too restrictive and block all results. Only use
        hard filters for well-defined metadata fields like mission/document_type.
        """
        filters = {}
        
        # Solo usar filtros hard para campos bien definidos
        # Misión y tipo de documento son campos estables en los metadatos
        if analysis.get('mission'):
            # CRITICAL: Normalize mission before filtering to ensure case-insensitive matching
            mission = analysis['mission']
            normalized_mission = MetadataNormalizer.normalize_mission(mission)
            if normalized_mission:
                filters['mission'] = normalized_mission
            else:
                # If normalization fails, use original but normalize case
                logger.warning(f"Failed to normalize mission '{mission}', using as-is")
                filters['mission'] = mission.upper().strip()
            
            # When a specific mission is mentioned, don't filter by document_type
            # This prevents excluding relevant documents (e.g., CHIME has document_type="general")
            # Document type filtering is only useful for general queries without a specific mission
        elif analysis.get('document_type'):
            # Only apply document_type filter if no specific mission was mentioned
            filters['document_type'] = analysis['document_type']
        
        # NOTA: Instrumentos y productos se manejan solo vía boost,
        # no como filtros hard, porque no todos los documentos tienen estos campos
        
        return filters
    
    def create_qdrant_filter(self, filters: Dict[str, any]) -> Optional[Dict[str, any]]:
        """Convierte filtros internos a formato simple compatible con QdrantClient."""
        if not filters:
            return None
        
        # Convertir a formato simple key-value que el cliente actual puede manejar
        simple_filters = {}
        
        for key, value in filters.items():
            if isinstance(value, (bool, str, int, float)):
                simple_filters[key] = value
            elif isinstance(value, list) and value:
                # Para listas, tomar el primer valor por simplicidad
                simple_filters[key] = value[0]
        
        return simple_filters if simple_filters else None
    
    def boost_scores_by_metadata(self, results: List[Dict], analysis: Dict[str, any]) -> List[Dict]:
        """Aplica boost a los scores basado en metadatos relevantes de Sentinel."""
        if not results:
            return results
        
        boosted_results = []
        
        for result in results:
            metadata = result.get('metadata', {})
            original_score = result.get('score', 0.0)
            boost_factor = 1.0
            boost_reasons = []
            
            # Boost por misión coincidente
            result_mission = metadata.get('mission')
            query_mission = analysis.get('mission')
            if query_mission and result_mission:
                # Normalizar misiones para comparación
                result_mission_norm = result_mission.upper().strip()
                query_mission_norm = query_mission.upper().strip()
                if result_mission_norm == query_mission_norm:
                    boost_factor *= 1.4
                    boost_reasons.append("mission_match")
            
            # Boost por instrumento mencionado
            query_instruments = analysis.get('instruments', [])
            if query_instruments:
                # Buscar instrumentos en el texto o metadatos
                text = (result.get('contextualized_text') or result.get('text', '')).lower()
                title = (result.get('title') or '').lower()
                full_text = f"{title} {text}"
                
                for instrument in query_instruments:
                    instrument_lower = instrument.lower()
                    if instrument_lower in full_text:
                        boost_factor *= 1.3
                        boost_reasons.append(f"instrument_match:{instrument}")
                        break  # Solo boost una vez por instrumento
            
            # Boost por producto mencionado
            query_products = analysis.get('products', [])
            if query_products:
                text = (result.get('contextualized_text') or result.get('text', '')).lower()
                title = (result.get('title') or '').lower()
                full_text = f"{title} {text}"
                
                for product in query_products:
                    product_lower = product.lower()
                    # Buscar L1, L2, L3, Level-1, etc.
                    if product_lower in full_text or f"level-{product_lower[1:]}" in full_text:
                        boost_factor *= 1.25
                        boost_reasons.append(f"product_match:{product}")
                        break
            
            # Boost por tipo de documento relevante
            query_doc_type = analysis.get('document_type')
            result_doc_type = metadata.get('document_type')
            if query_doc_type and result_doc_type:
                if query_doc_type == result_doc_type:
                    boost_factor *= 1.2
                    boost_reasons.append("document_type_match")
            
            # Boost por tipo de consulta
            query_type = analysis.get('query_type')
            if query_type == 'procedure':
                # Preferir documentos con listas o pasos numerados
                text = result.get('contextualized_text') or result.get('text', '')
                if re.search(r'\b(?:step|paso)\s*\d+', text, re.IGNORECASE):
                    boost_factor *= 1.15
                    boost_reasons.append("procedure_structure")
            elif query_type == 'definition':
                # Preferir documentos informativos
                if result_doc_type in ['mission_overview', 'general']:
                    boost_factor *= 1.1
                    boost_reasons.append("informational_content")
            
            # Boost por calidad del contenido
            word_count = metadata.get('word_count', 0)
            # Asegurar que word_count es un int
            try:
                word_count = int(word_count) if word_count else 0
            except (ValueError, TypeError):
                word_count = 0
            
            if 20 <= word_count <= 300:  # Chunks de tamaño óptimo
                boost_factor *= 1.05
                boost_reasons.append("optimal_length")
            
            # Aplicar boost
            boosted_score = original_score * boost_factor
            
            boosted_result = result.copy()
            boosted_result['score'] = boosted_score
            boosted_result['original_score'] = original_score
            boosted_result['boost_factor'] = boost_factor
            boosted_result['boost_reasons'] = boost_reasons
            
            boosted_results.append(boosted_result)
        
        # Re-ordenar por score boosteado
        boosted_results.sort(key=lambda x: x['score'], reverse=True)
        
        if self.enable_logging and boost_reasons:
            all_reasons = set()
            for r in boosted_results:
                all_reasons.update(r.get('boost_reasons', []))
            if all_reasons:
                logger.info(f"Applied boosts: {all_reasons}")
        
        return boosted_results
    
    def get_query_suggestions(self, query: str) -> List[str]:
        """Genera sugerencias de consultas mejoradas basadas en el análisis."""
        analysis = self.analyze_query(query)
        suggestions = []
        
        # Sugerencias basadas en misión
        if analysis.get('mission'):
            mission = analysis['mission']
            if 'product' not in query.lower():
                suggestions.append(f"{query} products")
            if 'instrument' not in query.lower():
                suggestions.append(f"{query} instruments")
        
        # Sugerencias basadas en tipo de consulta
        if analysis['query_type'] == 'general':
            if 'mission' in query.lower():
                suggestions.append(f"{query} overview")
                suggestions.append(f"{query} specifications")
        
        return suggestions[:3]  # Máximo 3 sugerencias


class SmartMetadataExtractor:
    """Extractor inteligente de metadatos para Sentinel Missions."""
    
    def __init__(self):
        self.filter = MetadataFilter()
    
    def extract_filters(self, query: str) -> Optional[Dict[str, str]]:
        """Extrae filtros de metadatos de una consulta."""
        analysis = self.filter.analyze_query(query)
        
        # Convertir a formato simple para compatibilidad
        simple_filters = {}
        
        if analysis.get('mission'):
            # CRITICAL: Normalize mission before filtering to ensure case-insensitive matching
            # This prevents failures when extracted mission doesn't match stored format
            mission = analysis['mission']
            normalized_mission = MetadataNormalizer.normalize_mission(mission)
            if normalized_mission:
                simple_filters['mission'] = normalized_mission
            else:
                # If normalization fails, use original but log warning
                logger.warning(f"Failed to normalize mission '{mission}', using as-is")
                simple_filters['mission'] = mission.upper().strip()  # At least normalize case
            
            # When a specific mission is mentioned, don't filter by document_type
            # This prevents excluding relevant documents (e.g., CHIME has document_type="general")
            # Document type filtering is only useful for general queries without a specific mission
        elif analysis.get('document_type'):
            # Only apply document_type filter if no specific mission was mentioned
            simple_filters['document_type'] = analysis['document_type']
        
        return simple_filters if simple_filters else None
    
    def get_qdrant_filters(self, query: str) -> Optional[Dict[str, any]]:
        """Obtiene filtros en formato Qdrant.
        
        Solo devuelve filtros hard para campos bien definidos (mission, document_type).
        Instrumentos y productos se manejan vía boost, no filtros.
        """
        analysis = self.filter.analyze_query(query)
        filters = self.filter._generate_filters(analysis)
        return self.filter.create_qdrant_filter(filters)
    
    def enhance_results(self, query: str, results: List[Dict]) -> List[Dict]:
        """Mejora los resultados aplicando boost basado en metadatos."""
        analysis = self.filter.analyze_query(query)
        return self.filter.boost_scores_by_metadata(results, analysis)
