"""
Export utilities for activity records to CSV and PDF formats
"""
import csv
import io
from datetime import datetime
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import os

# Maximum records per export to prevent memory/timeout issues
MAX_EXPORT_RECORDS = 10000


def export_to_csv(queryset, fields, filename_prefix):
    """
    Export queryset to CSV format
    
    Args:
        queryset: Django queryset to export
        fields: List of field names to include
        filename_prefix: Prefix for the exported filename
    
    Returns:
        HttpResponse with CSV file
    """
    response = HttpResponse(content_type='text/csv')
    filename = f'{filename_prefix}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    # Write header
    writer.writerow(fields)
    
    # Write data rows
    for obj in queryset:
        row = []
        for field in fields:
            value = obj
            for attr in field.split('__'):
                try:
                    value = getattr(value, attr)
                except AttributeError:
                    value = '-'
                    break
            # Handle callable methods
            if callable(value):
                value = value()
            row.append(str(value) if value is not None else '-')
        writer.writerow(row)
    
    return response


def export_assessments_to_csv(queryset, filter_info=None):
    """Export assessment records to CSV"""
    try:
        # Check record count
        total_count = queryset.count()
        if total_count > MAX_EXPORT_RECORDS:
            return JsonResponse({
                'error': f'Export limit exceeded. Maximum {MAX_EXPORT_RECORDS:,} records allowed. Found {total_count:,} records. Please apply filters to reduce the dataset.'
            }, status=400)
        
        if total_count == 0:
            return JsonResponse({
                'error': 'No records found to export. Please adjust your filters.'
            }, status=400)
        
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        filename = f'assessments_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Add metadata header
        writer.writerow(['# Flood Risk Assessment Records Export'])
        writer.writerow([f'# Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}'])
        writer.writerow([f'# Total Records: {total_count}'])
        if filter_info:
            for key, value in filter_info.items():
                writer.writerow([f'# {key}: {value}'])
        writer.writerow([])  # Empty row
        
        # Column headers
        writer.writerow(['#', 'Barangay', 'Staff Member', 'Username', 'Latitude', 'Longitude', 'Risk Code', 'Description', 'Date'])
        
        # Data rows with row numbers
        for idx, obj in enumerate(queryset, 1):
            writer.writerow([
                idx,
                obj.barangay,
                obj.user.get_full_name(),
                obj.user.username,
                f'{obj.latitude:.6f}',
                f'{obj.longitude:.6f}',
                obj.flood_risk_code,
                obj.flood_risk_description,
                obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return response
    except Exception as e:
        return JsonResponse({
            'error': f'Failed to generate CSV export: {str(e)}'
        }, status=500)


def export_reports_to_csv(queryset, filter_info=None):
    """Export report records to CSV"""
    try:
        # Check record count
        total_count = queryset.count()
        if total_count > MAX_EXPORT_RECORDS:
            return JsonResponse({
                'error': f'Export limit exceeded. Maximum {MAX_EXPORT_RECORDS:,} records allowed. Found {total_count:,} records. Please apply filters to reduce the dataset.'
            }, status=400)
        
        if total_count == 0:
            return JsonResponse({
                'error': 'No records found to export. Please adjust your filters.'
            }, status=400)
        
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        filename = f'reports_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Add metadata header
        writer.writerow(['# Flood Risk Reports Export'])
        writer.writerow([f'# Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}'])
        writer.writerow([f'# Total Records: {total_count}'])
        if filter_info:
            for key, value in filter_info.items():
                writer.writerow([f'# {key}: {value}'])
        writer.writerow([])  # Empty row
        
        # Column headers
        writer.writerow(['#', 'Barangay', 'Staff Member', 'Username', 'Latitude', 'Longitude', 'Risk Code', 'Risk Label', 'Date'])
        
        # Data rows with row numbers
        for idx, obj in enumerate(queryset, 1):
            writer.writerow([
                idx,
                obj.barangay,
                obj.user.get_full_name(),
                obj.user.username,
                f'{obj.latitude:.6f}',
                f'{obj.longitude:.6f}',
                obj.flood_risk_code,
                obj.flood_risk_label,
                obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return response
    except Exception as e:
        return JsonResponse({
            'error': f'Failed to generate CSV export: {str(e)}'
        }, status=500)


def export_certificates_to_csv(queryset, filter_info=None):
    """Export certificate records to CSV"""
    try:
        # Check record count
        total_count = queryset.count()
        if total_count > MAX_EXPORT_RECORDS:
            return JsonResponse({
                'error': f'Export limit exceeded. Maximum {MAX_EXPORT_RECORDS:,} records allowed. Found {total_count:,} records. Please apply filters to reduce the dataset.'
            }, status=400)
        
        if total_count == 0:
            return JsonResponse({
                'error': 'No records found to export. Please adjust your filters.'
            }, status=400)
        
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        filename = f'certificates_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Add metadata header
        writer.writerow(['# Flood Risk Certificates Export'])
        writer.writerow([f'# Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}'])
        writer.writerow([f'# Total Records: {total_count}'])
        if filter_info:
            for key, value in filter_info.items():
                writer.writerow([f'# {key}: {value}'])
        writer.writerow([])  # Empty row
        
        # Column headers
        writer.writerow(['#', 'Establishment', 'Owner', 'Location', 'Barangay', 'Staff Member', 'Latitude', 'Longitude', 'Susceptibility', 'Zone Status', 'Date'])
        
        # Data rows with row numbers
        for idx, obj in enumerate(queryset, 1):
            writer.writerow([
                idx,
                obj.establishment_name,
                obj.owner_name,
                obj.location,
                obj.barangay,
                obj.user.get_full_name(),
                f'{obj.latitude:.6f}',
                f'{obj.longitude:.6f}',
                obj.flood_susceptibility,
                obj.zone_status,
                obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return response
    except Exception as e:
        return JsonResponse({
            'error': f'Failed to generate CSV export: {str(e)}'
        }, status=500)


def export_flood_activities_to_csv(queryset, filter_info=None):
    """Export flood record activities to CSV"""
    try:
        # Check record count
        total_count = queryset.count()
        if total_count > MAX_EXPORT_RECORDS:
            return JsonResponse({
                'error': f'Export limit exceeded. Maximum {MAX_EXPORT_RECORDS:,} records allowed. Found {total_count:,} records. Please apply filters to reduce the dataset.'
            }, status=400)
        
        if total_count == 0:
            return JsonResponse({
                'error': 'No records found to export. Please adjust your filters.'
            }, status=400)
        
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        filename = f'flood_activities_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Add metadata header
        writer.writerow(['# Flood Activity Records Export'])
        writer.writerow([f'# Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}'])
        writer.writerow([f'# Total Records: {total_count}'])
        if filter_info:
            for key, value in filter_info.items():
                writer.writerow([f'# {key}: {value}'])
        writer.writerow([])  # Empty row
        
        # Column headers
        writer.writerow(['#', 'Event Type', 'Action', 'Staff Member', 'Event Date', 'Affected Barangays', 'Total Casualties', 'Dead', 'Injured', 'Missing', 'Affected Persons', 'Affected Families', 'Damage (PHP)', 'Date'])
        
        # Data rows with row numbers
        for idx, obj in enumerate(queryset, 1):
            writer.writerow([
                idx,
                obj.event_type,
                obj.action,
                obj.user.get_full_name(),
                obj.event_date.strftime('%Y-%m-%d %H:%M:%S'),
                obj.affected_barangays,
                obj.total_casualties,
                obj.casualties_dead,
                obj.casualties_injured,
                obj.casualties_missing,
                obj.affected_persons,
                obj.affected_families,
                f'{obj.damage_total_php:,.2f}',
                obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return response
    except Exception as e:
        return JsonResponse({
            'error': f'Failed to generate CSV export: {str(e)}'
        }, status=500)


def export_user_logs_to_csv(queryset, filter_info=None):
    """Export user logs to CSV"""
    try:
        # Check record count
        total_count = queryset.count()
        if total_count > MAX_EXPORT_RECORDS:
            return JsonResponse({
                'error': f'Export limit exceeded. Maximum {MAX_EXPORT_RECORDS:,} records allowed. Found {total_count:,} records. Please apply filters to reduce the dataset.'
            }, status=400)
        
        if total_count == 0:
            return JsonResponse({
                'error': 'No records found to export. Please adjust your filters.'
            }, status=400)
        
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        filename = f'user_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        
        # Add metadata header
        writer.writerow(['# User Activity Logs Export'])
        writer.writerow([f'# Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}'])
        writer.writerow([f'# Total Records: {total_count}'])
        if filter_info:
            for key, value in filter_info.items():
                writer.writerow([f'# {key}: {value}'])
        writer.writerow([])  # Empty row
        
        # Column headers
        writer.writerow(['#', 'Action', 'Staff Member', 'Username', 'Position', 'Timestamp'])
        
        # Data rows with row numbers
        for idx, obj in enumerate(queryset, 1):
            # Get position display value
            if obj.user.position == 'others' and obj.user.custom_position:
                position_display = obj.user.custom_position
            else:
                position_display = obj.user.get_position_display() if hasattr(obj.user, 'get_position_display') else obj.user.position
            
            writer.writerow([
                idx,
                obj.action,
                obj.user.get_full_name(),
                obj.user.username,
                position_display or 'Not specified',
                obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return response
    except Exception as e:
        return JsonResponse({
            'error': f'Failed to generate CSV export: {str(e)}'
        }, status=500)


def export_to_pdf(title, headers, data, filename_prefix, filter_info=None, summary_stats=None):
    """
    Export data to PDF format with modern, clean design
    
    Args:
        title: PDF title
        headers: List of column headers
        data: List of lists containing row data
        filename_prefix: Prefix for the exported filename
        filter_info: Dictionary of applied filters
        summary_stats: Dictionary of summary statistics
    
    Returns:
        HttpResponse with PDF file or JsonResponse with error
    """
    try:
        # Check record count
        total_count = len(data)
        if total_count > MAX_EXPORT_RECORDS:
            return JsonResponse({
                'error': f'Export limit exceeded. Maximum {MAX_EXPORT_RECORDS:,} records allowed. Found {total_count:,} records. Please apply filters to reduce the dataset.'
            }, status=400)
        
        if total_count == 0:
            return JsonResponse({
                'error': 'No records found to export. Please adjust your filters.'
            }, status=400)
    
        # Create a buffer for the PDF
        buffer = io.BytesIO()
        
        response = HttpResponse(content_type='application/pdf')
        filename = f'{filename_prefix}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Custom page template with header and footer
        def add_header_footer(canvas, doc):
            canvas.saveState()
            
            # Header - DRRMO logo/header (full width, edge to edge)
            header_path = os.path.join(settings.STATIC_ROOT or settings.BASE_DIR / 'static', 'images', 'drrmo_header.png')
            if os.path.exists(header_path):
                try:
                    # Draw header from edge to edge (0 to page width)
                    page_width = letter[0]
                    canvas.drawImage(header_path, 0, doc.height + doc.topMargin, 
                                   width=page_width, height=1.2*inch, 
                                   preserveAspectRatio=True, mask='auto')
                except:
                    pass
            
            # Footer line
            page_width = letter[0]
            canvas.setStrokeColor(colors.HexColor('#1e3a5f'))
            canvas.setLineWidth(2)
            canvas.line(0.5*inch, 0.65*inch, page_width - 0.5*inch, 0.65*inch)
            
            # Footer text
            canvas.setFont('Helvetica-Bold', 10)
            canvas.setFillColor(colors.HexColor('#1e3a5f'))
            footer_text = "SILAY CITY DISASTER RISK REDUCTION & MANAGEMENT COUNCIL"
            text_width = canvas.stringWidth(footer_text, 'Helvetica-Bold', 10)
            canvas.drawString((page_width - text_width) / 2, 0.4*inch, footer_text)
            
            canvas.restoreState()
        
        # Create PDF with portrait orientation
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            topMargin=1.3*inch,
            bottomMargin=1*inch,
            leftMargin=0.5*inch,
            rightMargin=0.5*inch
        )
        elements = []
        styles = getSampleStyleSheet()
        
        # Modern color scheme - matching monitoring exports
        primary_color = colors.HexColor('#1e3a5f')
        secondary_color = colors.HexColor('#2563eb')
        light_bg = colors.HexColor('#f7fafc')
        border_color = colors.HexColor('#cbd5e0')
        text_dark = colors.HexColor('#4a5568')
        
        # Custom title style
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=20,
            textColor=primary_color,
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        # Subtitle style
        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Normal'],
            fontSize=12,
            textColor=primary_color,
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        # Title
        elements.append(Paragraph(title.upper(), title_style))
        elements.append(Paragraph('System Activity Records', subtitle_style))
        elements.append(Spacer(1, 0.15*inch))
        
        # Metadata box with professional styling
        metadata_style = ParagraphStyle(
            'Metadata',
            parent=styles['Normal'],
            fontSize=10,
            textColor=text_dark,
            leading=14,
            leftIndent=10,
            rightIndent=10
        )
        
        # Build metadata content
        metadata_lines = [f'<b>Report Generated:</b> {datetime.now().strftime("%B %d, %Y at %I:%M %p")}']
        if summary_stats:
            metadata_lines.append(f'<b>Total Records:</b> {summary_stats.get("total", len(data)):,} records')
        
        # Add filter information
        if filter_info:
            metadata_lines.append(f'<b>Filters Applied:</b> {len(filter_info)} active')
            for k, v in filter_info.items():
                metadata_lines.append(f'&nbsp;&nbsp;• <b>{k}:</b> {v}')
        
        metadata = '<para alignment="left">' + '<br/>'.join(metadata_lines) + '</para>'
        
        # Create a table for metadata with background
        metadata_table = Table([[Paragraph(metadata, metadata_style)]], colWidths=[6.5*inch])
        metadata_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), light_bg),
            ('BOX', (0, 0), (-1, -1), 1, border_color),
            ('TOPPADDING', (0, 0), (-1, -1), 18),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 18),
            ('LEFTPADDING', (0, 0), (-1, -1), 20),
            ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ]))
        elements.append(metadata_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Create paragraph style for table cells to enable text wrapping
        cell_style = ParagraphStyle(
            'CellText',
            parent=styles['Normal'],
            fontSize=8,
            textColor=text_dark,
            fontName='Helvetica',
            leading=10,
            wordWrap='CJK'
        )
        
        # Wrap data in Paragraph objects for proper text wrapping
        wrapped_data = []
        for idx, row in enumerate(data, 1):
            wrapped_row = [str(idx)]  # Row number as plain text
            for cell in row:
                # Wrap each cell content in a Paragraph for text wrapping
                wrapped_row.append(Paragraph(str(cell), cell_style))
            wrapped_data.append(wrapped_row)
        
        # Prepare table data with headers (add # column)
        table_headers = ['#'] + headers
        table_data = [table_headers] + wrapped_data
        
        # Dynamic column widths based on content type
        # Portrait letter: 8.5" width - 1.0" margins = 7.5" available
        available_width = 7.5 * inch
        
        # Allocate widths: row number column gets 0.3", distribute rest
        row_num_width = 0.3 * inch
        remaining_width = available_width - row_num_width
        
        # Smart column width allocation (can be customized per export type)
        num_cols = len(headers)
        col_widths = [row_num_width] + [remaining_width / num_cols] * num_cols
        
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # Professional table styling matching monitoring exports
        table.setStyle(TableStyle([
            # Header styling - navy blue background
            ('BACKGROUND', (0, 0), (-1, 0), primary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGNMENT', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            
            # Body styling - alternating rows
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, light_bg]),
            
            # Cell borders - subtle gray grid
            ('GRID', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e0')),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            
            # Text alignment and font
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TEXTCOLOR', (0, 1), (-1, -1), text_dark),
            ('ALIGNMENT', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 1), (-1, -1), 'TOP'),
        ]))
    
        elements.append(table)
        
        # Build PDF with header and footer
        doc.build(elements, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
        
        # Get the value of the BytesIO buffer and write it to the response
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        
        return response
    except Exception as e:
        return JsonResponse({
            'error': f'Failed to build PDF document: {str(e)}. The dataset may be too large or contain problematic characters.'
        }, status=500)


def prepare_assessments_data(queryset):
    """Prepare assessment data for PDF export"""
    headers = ['Barangay', 'Staff Member', 'Risk Code', 'Description', 'Coordinates', 'Date']
    data = []
    for obj in queryset:
        data.append([
            obj.barangay,
            obj.user.get_full_name(),
            obj.flood_risk_code,
            obj.flood_risk_description,
            f'{obj.latitude:.4f}, {obj.longitude:.4f}',
            obj.timestamp.strftime('%b %d, %Y')
        ])
    return headers, data


def prepare_reports_data(queryset):
    """Prepare reports data for PDF export"""
    headers = ['Barangay', 'Staff Member', 'Risk Code', 'Risk Label', 'Coordinates', 'Date']
    data = []
    for obj in queryset:
        data.append([
            obj.barangay,
            obj.user.get_full_name(),
            obj.flood_risk_code,
            obj.flood_risk_label,
            f'{obj.latitude:.4f}, {obj.longitude:.4f}',
            obj.timestamp.strftime('%b %d, %Y')
        ])
    return headers, data


def prepare_certificates_data(queryset):
    """Prepare certificates data for PDF export"""
    headers = ['Establishment', 'Owner', 'Location', 'Barangay', 'Susceptibility', 'Zone Status', 'Date']
    data = []
    for obj in queryset:
        data.append([
            obj.establishment_name,
            obj.owner_name,
            obj.location,
            obj.barangay,
            obj.flood_susceptibility,
            obj.zone_status,
            obj.timestamp.strftime('%b %d, %Y')
        ])
    return headers, data


def prepare_flood_activities_data(queryset):
    """Prepare flood activities data for PDF export"""
    headers = ['Event Type', 'Action', 'Staff Member', 'Affected Areas', 'Casualties', 'People', 'Damage (PHP)', 'Date']
    data = []
    for obj in queryset:
        data.append([
            obj.event_type,
            obj.action,
            obj.user.get_full_name(),
            obj.affected_barangays,
            f"{obj.total_casualties}",
            f"{obj.affected_persons} persons",
            f"₱{obj.damage_total_php:,.0f}",
            obj.timestamp.strftime('%b %d, %Y')
        ])
    return headers, data


def prepare_user_logs_data(queryset):
    """Prepare user logs data for PDF export"""
    headers = ['Action', 'Staff Member', 'Username', 'Position', 'Date & Time']
    data = []
    for obj in queryset:
        # Get position display value
        if obj.user.position == 'others' and obj.user.custom_position:
            position_display = obj.user.custom_position
        else:
            position_display = obj.user.get_position_display() if hasattr(obj.user, 'get_position_display') else obj.user.position
        
        # Smart truncation
        action = obj.action
        if len(action) > 30:
            action = action[:27] + '...'
        
        data.append([
            action,
            obj.user.get_full_name(),
            obj.user.username,
            position_display or 'Not specified',
            obj.timestamp.strftime('%b %d, %Y %I:%M %p')
        ])
    return headers, data
