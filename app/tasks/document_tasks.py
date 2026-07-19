"""
Document Tasks - 文档处理任务

包含执行文档解析和OCR识别的任务定义。
支持同步模式（CELERY_ENABLED=False）和异步模式（CELERY_ENABLED=True）。
"""
import logging
from app.core.celery_app import get_celery_app

celery_app = get_celery_app()
logger = logging.getLogger(__name__)


def _parse_document_sync(file_content: str, filename: str):
    """同步执行文档解析"""
    import base64
    from io import BytesIO
    from app.core.document_parser import DocumentParser
    
    logger.info(f"Starting document parse task, file: {filename}")
    
    try:
        file_bytes = base64.b64decode(file_content)
        parser = DocumentParser()
        result = parser.parse(BytesIO(file_bytes), filename)
        
        logger.info("Document parse task completed")
        return result
    except Exception as e:
        logger.error(f"Document parse task failed: {e}")
        raise


def _ocr_sync(image_content: str, page_number: int = 0):
    """同步执行OCR识别"""
    import base64
    from io import BytesIO
    from app.core.document_parser import DocumentParser
    
    logger.info(f"Starting OCR task, page: {page_number}")
    
    try:
        image_bytes = base64.b64decode(image_content)
        parser = DocumentParser()
        result = parser._parse_pdf_with_ocr(BytesIO(image_bytes))
        
        logger.info("OCR task completed")
        return result
    except Exception as e:
        logger.error(f"OCR task failed: {e}")
        raise


if celery_app:
    @celery_app.task(bind=True, name="document.parse")
    def parse_document_task(self, file_content: str, filename: str):
        """
        文档解析任务
        
        Args:
            file_content: Base64编码的文件内容
            filename: 文件名
        
        Returns:
            dict: 解析结果
        """
        return _parse_document_sync(file_content, filename)


    @celery_app.task(bind=True, name="document.ocr")
    def ocr_task(self, image_content: str, page_number: int = 0):
        """
        OCR识别任务
        
        Args:
            image_content: Base64编码的图片内容
            page_number: 页码（用于PDF多页识别）
        
        Returns:
            dict: OCR识别结果
        """
        return _ocr_sync(image_content, page_number)
else:
    def parse_document_task(file_content: str, filename: str):
        return _parse_document_sync(file_content, filename)
    
    def ocr_task(image_content: str, page_number: int = 0):
        return _ocr_sync(image_content, page_number)
