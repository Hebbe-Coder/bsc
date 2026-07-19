"""
Export Tasks - 导出任务

包含执行文档导出的任务定义。
支持同步模式（CELERY_ENABLED=False）和异步模式（CELERY_ENABLED=True）。
"""
import logging
from app.core.celery_app import get_celery_app

celery_app = get_celery_app()
logger = logging.getLogger(__name__)


def _export_word_sync(business_system: dict):
    """同步执行Word导出"""
    from exporters.word_exporter import WordExporter
    import base64
    
    logger.info("Starting Word export task")
    
    try:
        exporter = WordExporter()
        word_bytes = exporter.export(business_system)
        
        content_base64 = base64.b64encode(word_bytes).decode('utf-8')
        
        logger.info("Word export task completed")
        return {
            "content_base64": content_base64,
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "filename": "业务系统分析报告.docx",
        }
    except Exception as e:
        logger.error(f"Word export task failed: {e}")
        raise


def _export_pdf_sync(business_system: dict):
    """同步执行PDF导出"""
    from exporters.pdf_exporter import PDFExporter
    import base64
    
    logger.info("Starting PDF export task")
    
    try:
        exporter = PDFExporter()
        pdf_bytes = exporter.export(business_system)
        
        content_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        logger.info("PDF export task completed")
        return {
            "content_base64": content_base64,
            "mime_type": "application/pdf",
            "filename": "业务系统分析报告.pdf",
        }
    except Exception as e:
        logger.error(f"PDF export task failed: {e}")
        raise


def _export_markdown_sync(business_system: dict):
    """同步执行Markdown导出"""
    from exporters.markdown_exporter import MarkdownExporter
    
    logger.info("Starting Markdown export task")
    
    try:
        exporter = MarkdownExporter()
        content = exporter.export(business_system)
        
        logger.info("Markdown export task completed")
        return {
            "content": content,
            "mime_type": "text/markdown",
            "filename": "业务系统分析报告.md",
        }
    except Exception as e:
        logger.error(f"Markdown export task failed: {e}")
        raise


if celery_app:
    @celery_app.task(bind=True, name="export.word")
    def export_word_task(self, business_system: dict):
        """
        Word导出任务
        
        Args:
            business_system: 业务系统数据
        
        Returns:
            dict: 导出结果（包含Base64编码的Word文档）
        """
        return _export_word_sync(business_system)


    @celery_app.task(bind=True, name="export.pdf")
    def export_pdf_task(self, business_system: dict):
        """
        PDF导出任务
        
        Args:
            business_system: 业务系统数据
        
        Returns:
            dict: 导出结果（包含Base64编码的PDF文档）
        """
        return _export_pdf_sync(business_system)


    @celery_app.task(bind=True, name="export.markdown")
    def export_markdown_task(self, business_system: dict):
        """
        Markdown导出任务
        
        Args:
            business_system: 业务系统数据
        
        Returns:
            dict: 导出结果
        """
        return _export_markdown_sync(business_system)
else:
    def export_word_task(business_system: dict):
        return _export_word_sync(business_system)
    
    def export_pdf_task(business_system: dict):
        return _export_pdf_sync(business_system)
    
    def export_markdown_task(business_system: dict):
        return _export_markdown_sync(business_system)
