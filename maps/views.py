from django.core.serializers import serialize
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Barangay, FloodSusceptibility, AssessmentRecord, ReportRecord, CertificateRecord, FloodRecordActivity
from users.models import UserLog
from datetime import datetime
import io
import os
from django.conf import settings
from django.http import HttpResponse, JsonResponse

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

try:
    from . import export_utils
except ImportError:
    export_utils = None

from django.contrib.gis.geos import Point
from django.utils.html import escape

def get_risk_data_from_coords(lat, lon):
    """
    Look up the flood risk code and description from the database based on coordinates.
    This prevents users from tampering with risk levels via URL parameters.
    """
    try:
        # Create a Point object (longitude first for PostGIS)
        pnt = Point(float(lon), float(lat), srid=4326)
        
        # Check which barangay this point falls into (to verify barangay name)
        barangay = Barangay.objects.filter(geometry__intersects=pnt).first()
        barangay_name = barangay.name if barangay else "Unknown"

        # Define risk priority (higher value = higher risk)
        risk_priority = {'VHF': 4, 'HF': 3, 'MF': 2, 'LF': 1, 'Unknown': 0}
        
        # Find all susceptibility zones that intersect with the point
        zones = list(FloodSusceptibility.objects.filter(geometry__intersects=pnt))
        
        if not zones:
            return 'LF', 'Low Susceptibility; less than 0.5 meters flood height and/or less than 1 day flooding', barangay_name
            
        # Select the zone with the highest risk level
        best_zone = max(zones, key=lambda z: risk_priority.get(z.haz_code, 0))
        
        # Map descriptions (consistent with report_view logic)
        risk_descriptions = {
            'LF': 'Low Susceptibility; less than 0.5 meters flood height and/or less than 1 day flooding',
            'MF': 'Moderate Susceptibility; 0.5 to 1 meter flood height and/or 1 to 3 days flooding',
            'HF': 'High Susceptibility; 1 to 2 meters flood height and/or more than 3 days flooding',
            'VHF': 'Very High Susceptibility; more than 2 meters flood height and/or more than 3 days flooding'
        }
        
        return best_zone.haz_code, risk_descriptions.get(best_zone.haz_code, 'No assessment available'), barangay_name
        
    except (ValueError, TypeError, Exception):
        return 'Unknown', 'Unable to calculate risk for these coordinates.', 'Unknown'

@login_required
def error_view(request):
    """Display error message to user with sanitization"""
    # Sanitize inputs to prevent reflected XSS
    error_title = escape(request.GET.get('title', 'An Error Occurred'))
    error_message = escape(request.GET.get('message', 'Something went wrong. Please try again.'))
    error_details = escape(request.GET.get('details', ''))
    
    context = {
        'error_title': error_title,
        'error_message': error_message,
        'error_details': error_details,
    }
    
    return render(request, 'maps/error.html', context)

def privacy_policy_view(request):
    """Display Privacy Policy page"""
    return render(request, 'maps/privacy_policy.html')

def terms_of_service_view(request):
    """Display Terms of Service page"""
    return render(request, 'maps/terms_of_service.html')

@login_required
def map_view(request):
    from monitoring.models import RainfallData, WeatherData, TideLevelData
    from monitoring.views import get_flood_risk_level, get_tide_risk_level, get_combined_risk_level
    
    barangays = serialize('geojson', Barangay.objects.all(), geometry_field='geometry', fields=('id', 'name', 'parent_id', 'geometry'))
    flood_areas = serialize('geojson', FloodSusceptibility.objects.all(), geometry_field='geometry', fields=('lgu', 'psgc_lgu', 'haz_class', 'haz_code', 'haz_area_ha', 'geometry'))
    barangay_names = Barangay.objects.values_list('name', flat=True).order_by('name')
    
    # Get latest monitoring data (same as monitoring page, exclude null timestamps)
    rainfall_data = RainfallData.objects.filter(timestamp__isnull=False).first()
    weather_data = WeatherData.objects.filter(timestamp__isnull=False).first()
    tide_data = TideLevelData.objects.filter(timestamp__isnull=False).first()
    
    # Calculate risk levels using the same functions as monitoring page
    context = {
        'barangays_json': barangays,
        'flood_areas_json': flood_areas,
        'barangay_names': barangay_names,
        'rainfall_data': rainfall_data,
        'weather_data': weather_data,
        'tide_data': tide_data,
    }
    
    if rainfall_data:
        rain_risk_level, rain_risk_color = get_flood_risk_level(rainfall_data.value_mm)
        context['rain_risk'] = {'level': rain_risk_level, 'color': rain_risk_color}
        
    if tide_data:
        tide_risk_level, tide_risk_color = get_tide_risk_level(tide_data.height_m)
        context['tide_risk'] = {'level': tide_risk_level, 'color': tide_risk_color}
    
    if rainfall_data and tide_data:
        combined_risk_level, combined_risk_color = get_combined_risk_level(rainfall_data.value_mm, tide_data.height_m)
        context['combined_risk'] = {'level': combined_risk_level, 'color': combined_risk_color}
    
    return render(request, 'maps/map.html', context)

@login_required
def report_view(request):
    # Get parameters from URL
    latitude = request.GET.get('lat', '0.000000')
    longitude = request.GET.get('lon', '0.000000')
    
    # SECURITY: Validate coordinates and risk server-side
    risk_code, assessment_text, barangay = get_risk_data_from_coords(latitude, longitude)
    
    # Risk assessment and recommendation mapping
    risk_data = {
        'LF': {
            'label': 'Low Susceptibility; less than 0.5 meters flood height and/or less than 1 day flooding',
            'class': 'risk-low',
            'recommendation': 'Areas with low susceptibility to floods are likely to experience flood heights of less than 0.5 meters and/or flood duration of less than 1 day. These include low hills and gentle slopes that have sparse to moderate drainage density.\n\nThe implementation of appropriate mitigation measures as deemed necessary by project engineers and LGU building officials is recommended for areas that are susceptible to various flood depths. Site-specific studies including the assessment for other types of hazards should also be conducted to address potential foundation problems.'
        },
        'MF': {
            'label': 'Moderate Susceptibility; 0.5 to 1 meter flood height and/or 1 to 3 days flooding',
            'class': 'risk-moderate',
            'recommendation': 'Areas with moderate susceptibility to floods are likely to experience flood heights of 0.5 meters up to 1 meter and/or flood duration of 1 to 3 days. These are subject to widespread inundation during prolonged and extensive heavy rainfall or extreme weather conditions. Fluvial terraces, alluvial fans, and infilled valleys are also moderately subjected to flooding.\n\nThe implementation of appropriate mitigation measures as deemed necessary by project engineers and LGU building officials is recommended for areas that are susceptible to various flood depths. Site-specific studies including the assessment for other types of hazards should also be conducted to address potential foundation problems.'
        },
        'HF': {
            'label': 'High Susceptibility; 1 to 2 meters flood height and/or more than 3 days flooding',
            'class': 'risk-high',
            'recommendation': 'Areas with high susceptibility to floods are likely to experience flood heights of 1 meter up to 2 meters and/or flood duration of more than 3 days. Sites including active river channels, abandoned river channels, and areas along riverbanks, are immediately flooded during heavy rains of several hours and are prone to flash floods. These may be considered not suitable for permanent habitation but may be developed for alternative uses subject to the implementation of appropriate mitigation measures after conducting site-specific geotechnical studies as deemed necessary by project engineers and LGU building officials.\n\nThe implementation of appropriate mitigation measures as deemed necessary by project engineers and LGU building officials is recommended for areas that are susceptible to various flood depths. Site-specific studies including the assessment for other types of hazards should also be conducted to address potential foundation problems.'
        },
        'VHF': {
            'label': 'Very High Susceptibility; more than 2 meters flood height and/or more than 3 days flooding',
            'class': 'risk-very-high',
            'recommendation': 'Areas with very high susceptibility to floods are likely to experience flood heights of greater than 2 meters and/or flood duration of more than 3 days. These include active river channels, abandoned river channels, and areas along riverbanks, which are immediately flooded during heavy rains of several hours and are prone to flash floods. These are considered critical geohazard areas and are not suitable for development. It is recommended that these be declared as "No Habitation/No Build Zones" by the LGU, and that affected households/communities be relocated.\n\nThe implementation of appropriate mitigation measures as deemed necessary by project engineers and LGU building officials is recommended for areas that are susceptible to various flood depths. Site-specific studies including the assessment for other types of hazards should also be conducted to address potential foundation problems.'
        }
    }
    
    # Get the appropriate risk data or use default
    current_risk = risk_data.get(risk_code, {
        'label': 'Unknown Risk Level',
        'class': '',
        'recommendation': 'Please conduct a proper assessment.'
    })
    
    # Save report generation record
    ReportRecord.objects.create(
        user=request.user,
        barangay=barangay,
        latitude=latitude,
        longitude=longitude,
        flood_risk_code=risk_code,
        flood_risk_label=current_risk['label']
    )
    
    # Format current date
    current_date = datetime.now().strftime('%d %B %Y, %I:%M %p')
    
    # Create the in-memory PDF buffer
    buffer = io.BytesIO()
    
    # Page setup - A4 size in portrait orientation
    # A4: 595.27 x 841.89 points
    # Printable area: width = 595 - 72 = 523 points
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=125,
        bottomMargin=60
    )
    
    # Custom watermark and page template routine
    def add_watermark_and_header(canvas, doc_template):
        canvas.saveState()
        page_width, page_height = A4
        
        # 1. Draw Official Header Banner (100% scaled to margins)
        header_path = os.path.join(settings.BASE_DIR, 'silay_drrmo/static/images/drrmo_header.png')
        if os.path.exists(header_path):
            try:
                header_height = 80
                canvas.drawImage(header_path, 36, page_height - 36 - header_height, 
                                 width=page_width - 72, height=header_height, 
                                 preserveAspectRatio=True, mask='auto')
            except Exception:
                pass
                
        # 2. Draw Subtle Circular Watermark Logo
        logo_path = os.path.join(settings.BASE_DIR, 'silay_drrmo/static/images/drrmo_logo.png')
        if os.path.exists(logo_path):
            try:
                watermark_size = 280
                x_pos = (page_width - watermark_size) / 2
                y_pos = (page_height - watermark_size) / 2
                
                canvas.saveState()
                canvas.setFillAlpha(0.04)  # very subtle faded transparency
                canvas.drawImage(logo_path, x_pos, y_pos, 
                                 width=watermark_size, height=watermark_size, 
                                 preserveAspectRatio=True, mask='auto')
                canvas.restoreState()
            except Exception:
                pass

        # 3. Draw Document Footer line & branding text
        canvas.setStrokeColor(colors.HexColor('#0f172a'))
        canvas.setLineWidth(1.5)
        canvas.line(36, 45, page_width - 36, 45)
        
        canvas.setFont('Helvetica-Bold', 9)
        canvas.setFillColor(colors.HexColor('#0f172a'))
        footer_text = "SILAY CITY DISASTER RISK REDUCTION & MANAGEMENT COUNCIL"
        text_width = canvas.stringWidth(footer_text, 'Helvetica-Bold', 9)
        canvas.drawString((page_width - text_width) / 2, 30, footer_text)
        
        canvas.restoreState()

    # Define custom formatting styles
    styles = getSampleStyleSheet()
    
    meta_label_style = ParagraphStyle(
        'MetaLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#475569')
    )
    
    meta_val_style = ParagraphStyle(
        'MetaValue',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor('#0f172a')
    )
    
    meta_mono_style = ParagraphStyle(
        'MetaMono',
        parent=styles['Normal'],
        fontName='Courier-Bold',
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor('#0f172a')
    )
    
    title_style = ParagraphStyle(
        'ReportTitle',
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#0f172a'),
        spaceBefore=15,
        spaceAfter=15,
    )
    
    table_header_style = ParagraphStyle(
        'TableHeader',
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1e293b')
    )
    
    table_body_center_style = ParagraphStyle(
        'TableBodyCenter',
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#0f172a')
    )
    
    table_body_justify_style = ParagraphStyle(
        'TableBodyJustify',
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor('#1e293b')
    )
    
    # Styled severity-coded hazard text ratings
    risk_lf_style = ParagraphStyle(
        'RiskLF', fontName='Helvetica-Bold', fontSize=10, leading=14, alignment=TA_CENTER, textColor=colors.HexColor('#059669')
    )
    risk_mf_style = ParagraphStyle(
        'RiskMF', fontName='Helvetica-Bold', fontSize=10, leading=14, alignment=TA_CENTER, textColor=colors.HexColor('#d97706')
    )
    risk_hf_style = ParagraphStyle(
        'RiskHF', fontName='Helvetica-Bold', fontSize=10, leading=14, alignment=TA_CENTER, textColor=colors.HexColor('#dc2626')
    )
    risk_vhf_style = ParagraphStyle(
        'RiskVHF', fontName='Helvetica-Bold', fontSize=10, leading=14, alignment=TA_CENTER, textColor=colors.HexColor('#991b1b')
    )
    
    risk_style_map = {
        'LF': risk_lf_style,
        'MF': risk_mf_style,
        'HF': risk_hf_style,
        'VHF': risk_vhf_style
    }
    selected_risk_style = risk_style_map.get(risk_code, risk_lf_style)
    
    disc_header_style = ParagraphStyle(
        'DiscHeader',
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor('#0f172a'),
        spaceBefore=15,
        spaceAfter=5
    )
    
    disc_note_style = ParagraphStyle(
        'DiscNote',
        fontName='Helvetica-BoldOblique',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#475569'),
        spaceAfter=8
    )
    
    disc_bullet_style = ParagraphStyle(
        'DiscBullet',
        fontName='Helvetica',
        fontSize=8,
        leading=11.5,
        textColor=colors.HexColor('#475569'),
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=6
    )
    
    story = []
    
    story.append(Spacer(1, 10))
    
    # Render Metadata Table
    meta_data = [
        [
            Paragraph("DATE GENERATED:", meta_label_style),
            Paragraph(current_date, meta_val_style),
            Paragraph("ADMINISTRATIVE AREA:", meta_label_style),
            Paragraph(f"Barangay {barangay}, Silay City", meta_val_style),
        ],
        [
            Paragraph("LATITUDE:", meta_label_style),
            Paragraph(f"{latitude}° N", meta_mono_style),
            Paragraph("LONGITUDE:", meta_label_style),
            Paragraph(f"{longitude}° E", meta_mono_style),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[110, 150, 130, 133])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('LINEBELOW', (0,0), (-1,0), 0.5, colors.HexColor('#e2e8f0')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1')),
    ]))
    story.append(meta_table)
    
    story.append(Paragraph("HYDRO-METEOROLOGICAL HAZARDS ASSESSMENT", title_style))
    
    # Formatted recommendation spacing
    formatted_rec = current_risk['recommendation'].replace('\n\n', '<br/><br/>')
    
    # Render Hazard Assessment Table
    table_data = [
        [
            Paragraph("<b>HAZARD</b>", table_header_style),
            Paragraph("<b>ASSESSMENT</b>", table_header_style),
            Paragraph("<b>EXPLANATION AND RECOMMENDED MITIGATION</b>", table_header_style)
        ],
        [
            Paragraph("<font color='#2563eb'><b>Flood Hazard</b></font>", table_body_center_style),
            Paragraph(current_risk['label'], selected_risk_style),
            Paragraph(formatted_rec, table_body_justify_style)
        ]
    ]
    
    assessment_table = Table(table_data, colWidths=[90, 160, 273])
    assessment_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('VALIGN', (0,0), (-1,0), 'MIDDLE'),
        ('VALIGN', (0,1), (0,1), 'MIDDLE'),
        ('VALIGN', (1,1), (1,1), 'MIDDLE'),
        ('VALIGN', (2,1), (2,1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 1.5, colors.HexColor('#0f172a')),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(assessment_table)
    
    # Render Guidelines & Bulleted Disclaimers
    story.append(Paragraph("Explanation and Recommendation Guidelines:", disc_header_style))
    story.append(Paragraph("Note:", disc_note_style))
    
    bullet_points = [
        "All hazard assessments are based on the available susceptibility maps and the coordinates of the user's selected location.",
        "Depending on the basemaps used and methods employed during mapping, discrepancies may be observed between location of hazards or exposure information and actual ground observations.",
        "In some areas, hazard assessment may be updated as new data become available for interpretation or as a result of major topographic changes due to onset of natural events.",
        "The possibility of both rain-induced landslide and flooding occurring is not disregarded. Because of the composite nature of MGB's 1:10,000-scale Rain-induced Landslide and Flood Susceptibility Maps, it spatially prioritizes the more frequently occurring and most damaging hazards in an area. Continuous updating is being done.",
        "For site-specific evaluation or construction of critical facilities, detailed engineering assessment and onsite geotechnical engineering survey may be required."
    ]
    
    for bp in bullet_points:
        story.append(Paragraph(f"• &nbsp; {bp}", disc_bullet_style))
        
    doc.build(story, onFirstPage=add_watermark_and_header)
    pdf_content = buffer.getvalue()
    buffer.close()
    
    # Direct stream PDF response to open natively in the browser
    response = HttpResponse(pdf_content, content_type='application/pdf')
    filename = f"SCDRRMO_Assessment_{longitude}_{latitude}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response

@login_required
def certificate_form_view(request):
    # Get parameters from URL
    latitude = request.GET.get('lat', '0.000000')
    longitude = request.GET.get('lon', '0.000000')
    
    # SECURITY: Validate coordinates and risk server-side
    risk_code, assessment_text, barangay = get_risk_data_from_coords(latitude, longitude)
    
    # Map risk codes to full susceptibility text
    risk_mapping = {
        'LF': 'LOW FLOOD SUSCEPTIBILITY',
        'MF': 'MODERATE FLOOD SUSCEPTIBILITY',
        'HF': 'HIGH FLOOD SUSCEPTIBILITY',
        'VHF': 'VERY HIGH FLOOD SUSCEPTIBILITY'
    }
    
    # Map risk codes to zone status
    zone_mapping = {
        'LF': 'SAFE ZONE',
        'MF': 'CONTROLLED ZONE',
        'HF': 'CRITICAL ZONE',
        'VHF': 'NO HABITATION/BUILD ZONE'
    }
    
    flood_susceptibility = risk_mapping.get(risk_code, 'UNKNOWN FLOOD SUSCEPTIBILITY')
    zone_status = zone_mapping.get(risk_code, '')
    
    # Generate current date with proper suffix
    from datetime import datetime
    today = datetime.now()
    day = today.day
    
    # Add suffix to day
    if 4 <= day <= 20 or 24 <= day <= 30:
        suffix = "th"
    else:
        suffix = ["st", "nd", "rd"][day % 10 - 1]
    
    issue_date = f"{day}{suffix} of {today.strftime('%B %Y')}"
    
    context = {
        'barangay': barangay,
        'latitude': latitude,
        'longitude': longitude,
        'risk_code': risk_code,
        'flood_susceptibility': flood_susceptibility,
        'zone_status': zone_status,
        'issue_date': issue_date,
    }
    
    return render(request, 'maps/certificate_form.html', context)

@login_required
def certificate_view(request):
    if request.method == 'POST':
        from django.conf import settings
        
        # Get common form data and sanitize
        certificate_type = request.POST.get('certificate_type', 'STANDARD')
        location = escape(request.POST.get('location', ''))
        latitude = request.POST.get('latitude', '0.000000')
        longitude = request.POST.get('longitude', '0.000000')
        
        # SECURITY: Re-calculate risk and barangay server-side to prevent tampering
        risk_code, assessment_text, barangay = get_risk_data_from_coords(latitude, longitude)
        
        # SECURITY: Use signatory details from settings instead of POST
        signatory_name = getattr(settings, 'CERTIFICATE_SIGNATORY_NAME', 'P/SUPT. ALEXANDER A. MUÑOZ (RET.)')
        signatory_title = getattr(settings, 'CERTIFICATE_SIGNATORY_TITLE', 'DRRMO Officer IV')
        signatory_subtitle = getattr(settings, 'CERTIFICATE_SIGNATORY_SUBTITLE', 'Secretariat, SCDRRMC')
        
        # Map risk codes to full susceptibility text and zone status
        risk_mapping = {
            'LF': 'LOW FLOOD SUSCEPTIBILITY',
            'MF': 'MODERATE FLOOD SUSCEPTIBILITY',
            'HF': 'HIGH FLOOD SUSCEPTIBILITY',
            'VHF': 'VERY HIGH FLOOD SUSCEPTIBILITY'
        }
        
        zone_mapping = {
            'LF': 'SAFE ZONE',
            'MF': 'CONTROLLED ZONE',
            'HF': 'CRITICAL ZONE',
            'VHF': 'NO HABITATION/BUILD ZONE'
        }
        
        flood_susceptibility = risk_mapping.get(risk_code, 'UNKNOWN FLOOD SUSCEPTIBILITY')
        zone_status = zone_mapping.get(risk_code, 'UNKNOWN ZONE')
        
        # Generate current date with proper suffix
        from datetime import datetime
        today = datetime.now()
        day = today.day
        
        if 4 <= day <= 20 or 24 <= day <= 30:
            suffix = "th"
        else:
            suffix = ["st", "nd", "rd"][day % 10 - 1]
        
        issue_date = f"{day}{suffix} of {today.strftime('%B %Y')}"
        
        if certificate_type == 'SPECIAL':
            # Process SPECIAL Certification
            purok_name = escape(request.POST.get('purok_name', ''))
            incident_record = escape(request.POST.get('incident_record', 'SEVERAL'))
            intended_purpose = escape(request.POST.get('intended_purpose', ''))
            
            # Suitability logic: HF and VHF are typically NOT SUITABLE
            is_suitable = risk_code not in ['HF', 'VHF']
            suitability_status = "SUITABLE" if is_suitable else "NOT SUITABLE"
            
            # Map risk codes to special descriptions for the summary paragraph
            desc_mapping = {
                'LF': 'Low Flood-Prone Area',
                'MF': 'Moderate Flood-Prone Area',
                'HF': 'High Flood-Prone Area and High-Risk Area',
                'VHF': 'Very High Flood-Prone Area and High-Risk Area'
            }
            flood_description = desc_mapping.get(risk_code, 'Flood-Prone Area')
            
            # Signatories: "Prepared By" comes from the current logged-in user
            prepared_by_name = request.user.get_full_name() or request.user.username
            prepared_by_title = request.user.position if hasattr(request.user, 'position') else "Staff Member"
            # Get human-readable position if choices are used
            if hasattr(request.user, 'get_position_display'):
                prepared_by_title = request.user.get_position_display()

            # Save Special Certificate record
            CertificateRecord.objects.create(
                user=request.user,
                certificate_type='SPECIAL',
                location=location,
                barangay=barangay,
                latitude=latitude,
                longitude=longitude,
                flood_susceptibility=flood_susceptibility,
                zone_status=zone_status,
                issue_date=issue_date,
                purok_name=purok_name,
                incident_record=incident_record,
                intended_purpose=intended_purpose,
                is_suitable=is_suitable
            )
            
            # Dynamic PDF Setup - Special Certificate
            purok_name_up = purok_name.upper()
            barangay_up = barangay.upper()
            intended_purpose_up = intended_purpose.upper()
            
        else:
            # Process STANDARD Certificate
            establishment_name = escape(request.POST.get('establishment_name', ''))
            owner_name = escape(request.POST.get('owner_name', ''))
            
            # Get mitigating measures value from hidden field
            mitigating_measures_value = request.POST.get('mitigating_measures_value', 'false')
            
            # Save Standard Certificate record
            CertificateRecord.objects.create(
                user=request.user,
                certificate_type='STANDARD',
                establishment_name=establishment_name,
                owner_name=owner_name,
                location=location,
                barangay=barangay,
                latitude=latitude,
                longitude=longitude,
                flood_susceptibility=flood_susceptibility,
                zone_status=zone_status,
                issue_date=issue_date
            )
            
            barangay_up = barangay.upper()
            
        # RENDER REAL A4 REPORTLAB PDF STREAM
        buffer = io.BytesIO()
        
        # A4 coordinates: 595.27 x 841.89 points
        # Printable area: width = 595.27 - 108 = 487.27 points
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=54,
            rightMargin=54,
            topMargin=120,
            bottomMargin=54
        )
        
        def add_watermark_and_header(canvas, doc_template):
            canvas.saveState()
            page_width, page_height = A4
            
            # 1. Draw Official Header Banner (100% scaled to margins)
            header_path = os.path.join(settings.BASE_DIR, 'silay_drrmo/static/images/drrmo_header.png')
            if os.path.exists(header_path):
                try:
                    header_height = 80
                    canvas.drawImage(header_path, 54, page_height - 36 - header_height, 
                                     width=page_width - 108, height=header_height, 
                                     preserveAspectRatio=True, mask='auto')
                except Exception:
                    pass
                    
            # 2. Draw Subtle Circular Watermark Logo
            logo_path = os.path.join(settings.BASE_DIR, 'silay_drrmo/static/images/drrmo_logo.png')
            if os.path.exists(logo_path):
                try:
                    watermark_size = 280
                    x_pos = (page_width - watermark_size) / 2
                    y_pos = (page_height - watermark_size) / 2
                    
                    canvas.saveState()
                    canvas.setFillAlpha(0.03)  # very subtle faded transparency
                    canvas.drawImage(logo_path, x_pos, y_pos, 
                                     width=watermark_size, height=watermark_size, 
                                     preserveAspectRatio=True, mask='auto')
                    canvas.restoreState()
                except Exception:
                    pass

            # 3. Draw Document Footer line & branding text
            canvas.setStrokeColor(colors.black)
            canvas.setLineWidth(1.5)
            canvas.line(54, 55, page_width - 54, 55)
            
            canvas.setFont('Helvetica-Bold', 9)
            canvas.setFillColor(colors.black)
            footer_text = "SILAY CITY DISASTER RISK REDUCTION & MANAGEMENT COUNCIL"
            text_width = canvas.stringWidth(footer_text, 'Helvetica-Bold', 9)
            canvas.drawString((page_width - text_width) / 2, 40, footer_text)
            
            canvas.restoreState()

        # Custom Typography and Paragraph styles using ReportLab Times Roman defaults
        styles = getSampleStyleSheet()
        
        cert_title_style = ParagraphStyle(
            'CertTitle',
            fontName='Times-Bold',
            fontSize=22,
            leading=26,
            alignment=TA_CENTER,
            spaceAfter=20,
            spaceBefore=10
        )
        
        cert_body_style = ParagraphStyle(
            'CertBody',
            fontName='Times-Roman',
            fontSize=12.5,
            leading=18,
            alignment=TA_JUSTIFY,
            firstLineIndent=45,
            spaceAfter=10
        )
        
        cert_bold_title_style = ParagraphStyle(
            'CertBoldTitle',
            fontName='Times-Bold',
            fontSize=11,
            leading=13,
            spaceAfter=3
        )
        
        cert_sig_name_style = ParagraphStyle(
            'CertSigName',
            fontName='Times-Bold',
            fontSize=12,
            leading=14,
            spaceAfter=2
        )
        
        cert_sig_title_style = ParagraphStyle(
            'CertSigTitle',
            fontName='Times-Italic',
            fontSize=10.5,
            leading=12,
            spaceAfter=1
        )

        story = []
        
        # 1. Spaced title simulated for elegant certification header spacing
        story.append(Paragraph("C E R T I F I C A T I O N", cert_title_style))
        
        if certificate_type == 'SPECIAL':
            # SPECIAL Certificate Flowables
            p1 = (
                f"This is to certify that the area lot located at "
                f"<b>{purok_name_up}, BARANGAY {barangay_up}, SILAY CITY</b> "
                f"was assessed by the Silay City Disaster Risk Reduction & Management Office (SCDRRMO) "
                f"using MGB-DENR Map and SCDRRMO - FMSWGIS."
            )
            story.append(Paragraph(p1, cert_body_style))
            
            p2 = (
                f"<b>WHEREAS</b>, the above-mentioned lot is under "
                f"<b>{flood_susceptibility}</b> "
                f"as per MGB DETAILED LANDSLIDE AND FLOOD HAZARD MAP OF SILAY CITY, "
                f"NEGROS OCCIDENTAL, PHILIPPINES."
            )
            story.append(Paragraph(p2, cert_body_style))
            
            p3 = (
                f"<b>WHEREAS</b>, <b>{incident_record}</b> "
                f"flooding incidents had been recorded and experienced as per record on "
                f"historical data and past occurrences of Silay City DISASTER RISK REDUCTION "
                f"AND MANAGEMENT OFFICE."
            )
            story.append(Paragraph(p3, cert_body_style))
            
            p4 = (
                f"<b>WHEREFORE</b>, upon the assessment and evaluation conducted by the "
                f"Silay City Disaster Risk Reduction and Management Office (SCDRRMO), it has been determined "
                f"that the area lot located at <b>{purok_name_up}, BARANGAY {barangay_up}, SILAY CITY</b> "
                f"is situated within a <b>{flood_description}</b>, "
                f"and <b>{suitability_status}</b> for any "
                f"<b>{intended_purpose_up}</b>."
            )
            story.append(Paragraph(p4, cert_body_style))
            
            p5 = (
                f"THIS CERTIFICATION is issued by the undersigned as per request by the name/organization/address "
                f"mentioned above for whatever legal purposes it may serve."
            )
            story.append(Paragraph(p5, cert_body_style))
            
            p6 = (
                f"Issued this {issue_date}, at Silay City Disaster Risk Reduction & Management Office, "
                f"Silay City, Philippines."
            )
            story.append(Paragraph(p6, cert_body_style))
            
            # Double signature block side-by-side (using a 3-column table to split lines)
            signature_data = [
                [Paragraph("<b>PREPARED BY:</b>", cert_bold_title_style), "", Paragraph("<b>CERTIFIED BY:</b>", cert_bold_title_style)],
                ["", "", ""],
                [Paragraph(f"<b>{prepared_by_name.upper()}</b>", cert_sig_name_style), "", Paragraph(f"<b>{signatory_name.upper()}</b>", cert_sig_name_style)],
                [Paragraph(prepared_by_title, cert_sig_title_style), "", Paragraph(signatory_title, cert_sig_title_style)],
                [Paragraph("Silay City DRRM Office", cert_sig_title_style), "", Paragraph(signatory_subtitle, cert_sig_title_style)]
            ]
            sig_table = Table(signature_data, colWidths=[220, 47, 220])
            sig_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 1), (0, 1), 24),
                ('BOTTOMPADDING', (2, 1), (2, 1), 24),
                ('LINEBELOW', (0, 1), (0, 1), 1.5, colors.black),
                ('LINEBELOW', (2, 1), (2, 1), 1.5, colors.black),
                ('TOPPADDING', (0, 2), (-1, -1), 3),
            ]))
            
            story.append(Spacer(1, 20))
            story.append(KeepTogether([sig_table]))
            
        else:
            # STANDARD Certificate Flowables
            p1 = (
                f"This is to certify that the existing establishment named "
                f"<b>{establishment_name}</b> owned by "
                f"<b>{owner_name}</b> located at "
                f"<b>{location}</b>, "
                f"<b>BARANGAY {barangay_up}, SILAY CITY</b> "
                f"was assessed by the Silay City Disaster Risk Reduction & Management Office (SCDRRMO) "
                f"using MGB-DENR Map and SCDRRMO - FMSWGIS."
            )
            story.append(Paragraph(p1, cert_body_style))
            
            p2 = (
                f"<b>WHEREAS</b>, the above-mentioned lot is under "
                f"<b>{flood_susceptibility}</b> "
                f"as per MGB DETAILED FLOOD HAZARD MAP OF SILAY CITY, "
                f"NEGROS OCCIDENTAL, PHILIPPINES."
            )
            story.append(Paragraph(p2, cert_body_style))
            
            if mitigating_measures_value in ['true', True, 'True']:
                p3 = (
                    f"<b>WHEREAS</b>, Disaster Prevention and Mitigation are being established "
                    f"by the Silay City Disaster Risk Reduction & Management Council (SCDRRMC) to its possible hazard prone areas."
                )
                story.append(Paragraph(p3, cert_body_style))
                
                p4 = (
                    f"<b>WHEREAS</b>, Disaster Preparedness & Awareness Seminars are being conducted "
                    f"by the Silay City Disaster Risk Reduction & Management Office (SCDRRMO) to its surrounding communities."
                )
                story.append(Paragraph(p4, cert_body_style))
                
                p5 = (
                    f"<b>WHEREAS</b>, a Barangay Disaster Committee has been established by the "
                    f"Silay City Disaster Risk Reduction & Management Office (SCDRRMO), which will monitor and ensure "
                    f"the welfare and safety of its surrounding communities."
                )
                story.append(Paragraph(p5, cert_body_style))
            
            p6 = (
                f"<b>WHEREFORE</b>, upon assessment of the Silay City Disaster Risk Reduction & "
                f"Management Office (SCDRRMO), the existing establishment named "
                f"<b>{establishment_name}</b> owned by "
                f"<b>{owner_name}</b> located at "
                f"<b>{location}</b>, "
                f"<b>BARANGAY {barangay_up}, SILAY CITY</b> "
                f"is under a <u><b>{zone_status}</b></u>."
            )
            story.append(Paragraph(p6, cert_body_style))
            
            p7 = (
                f"Issued this {issue_date}, at Silay City Disaster Risk Reduction & Management Office, "
                f"Silay City, Philippines."
            )
            story.append(Paragraph(p7, cert_body_style))
            
            # Single right-aligned signature block
            signature_data = [
                ["", Paragraph("<b>CERTIFIED BY:</b>", cert_bold_title_style)],
                ["", ""],
                ["", Paragraph(f"<b>{signatory_name.upper()}</b>", cert_sig_name_style)],
                ["", Paragraph(signatory_title, cert_sig_title_style)],
                ["", Paragraph(signatory_subtitle, cert_sig_title_style)]
            ]
            sig_table = Table(signature_data, colWidths=[240, 247])
            sig_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (1, 1), (1, 1), 24),
                ('LINEBELOW', (1, 1), (1, 1), 1.5, colors.black),
                ('TOPPADDING', (1, 2), (1, -1), 3),
            ]))
            
            story.append(Spacer(1, 20))
            story.append(KeepTogether([sig_table]))

        # Build the document
        doc.build(story, onFirstPage=add_watermark_and_header, onLaterPages=add_watermark_and_header)
        
        pdf_content = buffer.getvalue()
        buffer.close()
        
        # Return as dynamic inline PDF stream!
        filename = f"SCDRRMO_Certification_{longitude}_{latitude}.pdf"
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response

    
    # If not POST, redirect to form
    return redirect('map_view')

# New view for saving assessments via AJAX
@login_required
def save_assessment(request):
    from django.http import JsonResponse
    
    if request.method == 'POST':
        latitude = request.POST.get('latitude', '0.000000')
        longitude = request.POST.get('longitude', '0.000000')
        
        # SECURITY: Validate coordinates and risk server-side
        flood_risk_code, flood_risk_description, barangay = get_risk_data_from_coords(latitude, longitude)
        
        # Save assessment record
        assessment = AssessmentRecord.objects.create(
            user=request.user,
            barangay=barangay,
            latitude=latitude,
            longitude=longitude,
            flood_risk_code=flood_risk_code,
            flood_risk_description=flood_risk_description
        )
        
        return JsonResponse({
            'success': True,
            'assessment_id': assessment.id,
            'message': 'Assessment saved successfully'
        })
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})

# View for staff to see their own activity history
@login_required
def my_activity(request):
    # Get sort parameter (default: recent first).
    # The UI uses `sort_order` in `my_activity.html` while `all_activities.html` uses `sort`.
    # Accept both for compatibility.
    sort_order = request.GET.get('sort') or request.GET.get('sort_order') or 'recent'
    
    # Exclude archived records from normal views
    assessments = AssessmentRecord.objects.filter(user=request.user, is_archived=False)
    reports = ReportRecord.objects.filter(user=request.user, is_archived=False)
    certificates = CertificateRecord.objects.filter(user=request.user, is_archived=False)
    flood_activities = FloodRecordActivity.objects.filter(user=request.user, is_archived=False)
    user_logs = UserLog.objects.filter(user=request.user, is_archived=False)
    
    # Apply ordering based on sort parameter
    if sort_order == 'oldest':
        order_by = 'timestamp'  # Oldest first
    else:
        order_by = '-timestamp'  # Recent first (default)
    
    assessments = assessments.order_by(order_by)
    reports = reports.order_by(order_by)
    certificates = certificates.order_by(order_by)
    flood_activities = flood_activities.order_by(order_by)
    user_logs = user_logs.order_by(order_by)
    
    # Get active tab parameter
    active_tab = request.GET.get('tab', 'assessments')  # Default to assessments
    
    context = {
        'assessments': assessments,
        'reports': reports,
        'certificates': certificates,
        'flood_activities': flood_activities,
        'user_logs': user_logs,
        'sort_order': sort_order,
        'active_tab': active_tab,
        'total_assessments': assessments.count(),
        'total_reports': reports.count(),
        'total_certificates': certificates.count(),
        'total_flood_activities': flood_activities.count(),
        'total_user_logs': user_logs.count(),
    }
    
    return render(request, 'maps/my_activity.html', context)

# View for admin to see all staff activities with pagination
@login_required
def all_activities(request):
    from django.contrib.admin.views.decorators import staff_member_required
    from django.core.exceptions import PermissionDenied
    from django.core.paginator import Paginator
    from django.db.models import Q
    from datetime import datetime, timedelta
    from django.utils import timezone as tz
    
    if not request.user.is_staff:
        raise PermissionDenied
    
    # Get sort parameter (default: recent first)
    # Accept both 'sort' and 'sort_order' for compatibility with templates
    sort_order = request.GET.get('sort') or request.GET.get('sort_order') or 'recent'
    
    # Get page number for current tab
    assessments_page = request.GET.get('assessments_page', 1)
    reports_page = request.GET.get('reports_page', 1)
    certificates_page = request.GET.get('certificates_page', 1)
    flood_page = request.GET.get('flood_page', 1)
    logs_page = request.GET.get('logs_page', 1)
    
    # Exclude archived records from normal views
    assessments = AssessmentRecord.objects.filter(is_archived=False).select_related('user')
    reports = ReportRecord.objects.filter(is_archived=False).select_related('user')
    certificates = CertificateRecord.objects.filter(is_archived=False).select_related('user')
    flood_activities = FloodRecordActivity.objects.filter(is_archived=False).select_related('user')
    user_logs = UserLog.objects.filter(is_archived=False).select_related('user')
    
    # Apply ordering based on sort parameter
    if sort_order == 'oldest':
        assessments = assessments.order_by('timestamp')
        reports = reports.order_by('timestamp')
        certificates = certificates.order_by('timestamp')
        flood_activities = flood_activities.order_by('timestamp')
        user_logs = user_logs.order_by('timestamp')
    else:
        assessments = assessments.order_by('-timestamp')
        reports = reports.order_by('-timestamp')
        certificates = certificates.order_by('-timestamp')
        flood_activities = flood_activities.order_by('-timestamp')
        user_logs = user_logs.order_by('-timestamp')
    
    # Get filter parameters
    filter_user = request.GET.get('user', None)
    filter_date = request.GET.get('date', None)
    date_from = request.GET.get('date_from', None)
    date_to = request.GET.get('date_to', None)
    date_range = request.GET.get('date_range', None)  # Quick filter: 7, 30, 90, all
    search_query = request.GET.get('search', '').strip()
    active_tab = request.GET.get('tab', 'assessments')  # Default to assessments
    per_page = request.GET.get('per_page', '25')  # Items per page
    
    # Default to last 30 days if no filters applied
    show_all = request.GET.get('show_all', '')
    if not any([filter_user, filter_date, date_from, date_to, date_range, search_query, show_all]):
        date_range = '30'  # Default to last 30 days
    
    # Apply date range quick filters (use tz.now() — timezone-aware, required when USE_TZ=True)
    if date_range and date_range != 'all':
        try:
            days = int(date_range)
            start_date = tz.now() - timedelta(days=days)
            assessments = assessments.filter(timestamp__gte=start_date)
            reports = reports.filter(timestamp__gte=start_date)
            certificates = certificates.filter(timestamp__gte=start_date)
            flood_activities = flood_activities.filter(timestamp__gte=start_date)
            user_logs = user_logs.filter(timestamp__gte=start_date)
        except ValueError:
            pass
    
    # Apply custom date range
    if date_from:
        try:
            start_date = datetime.strptime(date_from, '%Y-%m-%d')
            assessments = assessments.filter(timestamp__date__gte=start_date)
            reports = reports.filter(timestamp__date__gte=start_date)
            certificates = certificates.filter(timestamp__date__gte=start_date)
            flood_activities = flood_activities.filter(timestamp__date__gte=start_date)
            user_logs = user_logs.filter(timestamp__date__gte=start_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            end_date = datetime.strptime(date_to, '%Y-%m-%d')
            assessments = assessments.filter(timestamp__date__lte=end_date)
            reports = reports.filter(timestamp__date__lte=end_date)
            certificates = certificates.filter(timestamp__date__lte=end_date)
            flood_activities = flood_activities.filter(timestamp__date__lte=end_date)
            user_logs = user_logs.filter(timestamp__date__lte=end_date)
        except ValueError:
            pass
    
    # Apply user filter
    if filter_user:
        assessments = assessments.filter(user__id=filter_user)
        reports = reports.filter(user__id=filter_user)
        certificates = certificates.filter(user__id=filter_user)
        flood_activities = flood_activities.filter(user__id=filter_user)
        user_logs = user_logs.filter(user__id=filter_user)
    
    # Apply single date filter (exact date)
    if filter_date:
        assessments = assessments.filter(timestamp__date=filter_date)
        reports = reports.filter(timestamp__date=filter_date)
        certificates = certificates.filter(timestamp__date=filter_date)
        flood_activities = flood_activities.filter(timestamp__date=filter_date)
        user_logs = user_logs.filter(timestamp__date=filter_date)
    
    # Apply search filter
    if search_query:
        # Search in assessments (barangay, risk code, risk description)
        assessments = assessments.filter(
            Q(barangay__icontains=search_query) |
            Q(flood_risk_code__icontains=search_query) |
            Q(flood_risk_description__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
        
        # Search in reports (barangay, risk code, risk label)
        reports = reports.filter(
            Q(barangay__icontains=search_query) |
            Q(flood_risk_code__icontains=search_query) |
            Q(flood_risk_label__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
        
        # Search in certificates (establishment name, owner, barangay, location)
        certificates = certificates.filter(
            Q(establishment_name__icontains=search_query) |
            Q(owner_name__icontains=search_query) |
            Q(barangay__icontains=search_query) |
            Q(location__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
        
        # Search in flood activities (event type, affected barangays)
        flood_activities = flood_activities.filter(
            Q(event_type__icontains=search_query) |
            Q(affected_barangays__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
        
        # Search in user logs (action, username)
        user_logs = user_logs.filter(
            Q(action__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
    
    # Get total counts before pagination
    total_assessments = assessments.count()
    total_reports = reports.count()
    total_certificates = certificates.count()
    total_flood_activities = flood_activities.count()
    total_user_logs = user_logs.count()
    
    # Get unfiltered totals for statistics (excluding archived)
    unfiltered_assessments = AssessmentRecord.objects.filter(is_archived=False).count()
    unfiltered_reports = ReportRecord.objects.filter(is_archived=False).count()
    unfiltered_certificates = CertificateRecord.objects.filter(is_archived=False).count()
    unfiltered_flood = FloodRecordActivity.objects.filter(is_archived=False).count()
    unfiltered_logs = UserLog.objects.filter(is_archived=False).count()
    
    # Apply pagination with configurable page size
    try:
        paginator_size = int(per_page)
        if paginator_size not in [10, 25, 50, 100]:
            paginator_size = 25
    except ValueError:
        paginator_size = 25
    
    assessments_paginator = Paginator(assessments, paginator_size)
    assessments = assessments_paginator.get_page(assessments_page)
    
    reports_paginator = Paginator(reports, paginator_size)
    reports = reports_paginator.get_page(reports_page)
    
    certificates_paginator = Paginator(certificates, paginator_size)
    certificates = certificates_paginator.get_page(certificates_page)
    
    flood_paginator = Paginator(flood_activities, paginator_size)
    flood_activities = flood_paginator.get_page(flood_page)
    
    logs_paginator = Paginator(user_logs, paginator_size)
    user_logs = logs_paginator.get_page(logs_page)
    
    # Get all users for filter dropdown
    from django.contrib.auth import get_user_model
    User = get_user_model()
    users = User.objects.filter(is_active=True).order_by('username')
    
    context = {
        'assessments': assessments,
        'reports': reports,
        'certificates': certificates,
        'flood_activities': flood_activities,
        'user_logs': user_logs,
        'users': users,
        'filter_user': filter_user,
        'filter_date': filter_date,
        'date_from': date_from,
        'date_to': date_to,
        'date_range': date_range,
        'search_query': search_query,
        'sort_order': sort_order,
        'active_tab': active_tab,
        'per_page': per_page,
        'total_assessments': total_assessments,
        'total_reports': total_reports,
        'total_certificates': total_certificates,
        'total_flood_activities': total_flood_activities,
        'total_user_logs': total_user_logs,
        'unfiltered_assessments': unfiltered_assessments,
        'unfiltered_reports': unfiltered_reports,
        'unfiltered_certificates': unfiltered_certificates,
        'unfiltered_flood': unfiltered_flood,
        'unfiltered_logs': unfiltered_logs,
        'assessments_paginator': assessments_paginator,
        'reports_paginator': reports_paginator,
        'certificates_paginator': certificates_paginator,
        'flood_paginator': flood_paginator,
        'logs_paginator': logs_paginator,
        'filters_applied': bool(filter_user or filter_date or date_from or date_to or date_range or search_query),
    }
    
    return render(request, 'maps/all_activities.html', context)


# Export activities view
@login_required
def export_activities(request):
    """Export activities in CSV or PDF format"""
    from django.core.exceptions import PermissionDenied
    from django.http import JsonResponse
    
    if not request.user.is_staff:
        raise PermissionDenied
    
    # Check if export_utils is available
    if export_utils is None:
        return JsonResponse({
            'error': 'PDF export requires reportlab. Please run: pip install reportlab'
        }, status=500)
    
    export_type = request.GET.get('type', 'csv')  # csv or pdf
    activity_type = request.GET.get('activity', 'assessments')  # Type of activity to export
    
    # Get filter parameters
    filter_user = request.GET.get('user', None)
    filter_date = request.GET.get('date', None)
    date_from = request.GET.get('date_from', None)
    date_to = request.GET.get('date_to', None)
    date_range = request.GET.get('date_range', None)
    search_query = request.GET.get('search', '').strip()
    sort_order = request.GET.get('sort', 'recent')
    
    # Build filter_info dictionary
    from datetime import datetime, timedelta
    filter_info = {}
    if filter_user:
        from users.models import CustomUser
        try:
            user = CustomUser.objects.get(id=filter_user)
            filter_info['Staff Filter'] = f"{user.get_full_name()} ({user.username})"
        except CustomUser.DoesNotExist:
            pass
    if filter_date:
        filter_info['Date Filter'] = filter_date
    if date_from and date_to:
        filter_info['Date Range'] = f"{date_from} to {date_to}"
    elif date_from:
        filter_info['Date From'] = date_from
    elif date_to:
        filter_info['Date To'] = date_to
    if date_range and date_range != 'all':
        range_labels = {'7': 'Last 7 Days', '30': 'Last 30 Days', '90': 'Last 90 Days'}
        filter_info['Quick Filter'] = range_labels.get(date_range, f'Last {date_range} Days')
    if search_query:
        filter_info['Search Query'] = search_query
    filter_info['Sort Order'] = 'Oldest First' if sort_order == 'oldest' else 'Recent First'
    
    # Prepare base querysets (excluding archived records)
    assessments = AssessmentRecord.objects.filter(is_archived=False).select_related('user')
    reports = ReportRecord.objects.filter(is_archived=False).select_related('user')
    certificates = CertificateRecord.objects.filter(is_archived=False).select_related('user')
    flood_activities = FloodRecordActivity.objects.filter(is_archived=False).select_related('user')
    user_logs = UserLog.objects.filter(is_archived=False).select_related('user')
    
    # Apply ordering
    if sort_order == 'oldest':
        assessments = assessments.order_by('timestamp')
        reports = reports.order_by('timestamp')
        certificates = certificates.order_by('timestamp')
        flood_activities = flood_activities.order_by('timestamp')
        user_logs = user_logs.order_by('timestamp')
    else:
        assessments = assessments.order_by('-timestamp')
        reports = reports.order_by('-timestamp')
        certificates = certificates.order_by('-timestamp')
        flood_activities = flood_activities.order_by('-timestamp')
        user_logs = user_logs.order_by('-timestamp')
    
    # Apply date range quick filters (use timezone.now() to avoid naive datetime RuntimeWarning)
    if date_range and date_range != 'all':
        try:
            from django.utils import timezone as tz
            days = int(date_range)
            start_date = tz.now() - timedelta(days=days)
            assessments = assessments.filter(timestamp__gte=start_date)
            reports = reports.filter(timestamp__gte=start_date)
            certificates = certificates.filter(timestamp__gte=start_date)
            flood_activities = flood_activities.filter(timestamp__gte=start_date)
            user_logs = user_logs.filter(timestamp__gte=start_date)
        except ValueError:
            pass
    
    # Apply custom date range
    if date_from:
        try:
            start_date = datetime.strptime(date_from, '%Y-%m-%d')
            assessments = assessments.filter(timestamp__date__gte=start_date)
            reports = reports.filter(timestamp__date__gte=start_date)
            certificates = certificates.filter(timestamp__date__gte=start_date)
            flood_activities = flood_activities.filter(timestamp__date__gte=start_date)
            user_logs = user_logs.filter(timestamp__date__gte=start_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            end_date = datetime.strptime(date_to, '%Y-%m-%d')
            assessments = assessments.filter(timestamp__date__lte=end_date)
            reports = reports.filter(timestamp__date__lte=end_date)
            certificates = certificates.filter(timestamp__date__lte=end_date)
            flood_activities = flood_activities.filter(timestamp__date__lte=end_date)
            user_logs = user_logs.filter(timestamp__date__lte=end_date)
        except ValueError:
            pass
    
    # Apply filters
    if filter_user:
        assessments = assessments.filter(user__id=filter_user)
        reports = reports.filter(user__id=filter_user)
        certificates = certificates.filter(user__id=filter_user)
        flood_activities = flood_activities.filter(user__id=filter_user)
        user_logs = user_logs.filter(user__id=filter_user)
    
    if filter_date:
        assessments = assessments.filter(timestamp__date=filter_date)
        reports = reports.filter(timestamp__date=filter_date)
        certificates = certificates.filter(timestamp__date=filter_date)
        flood_activities = flood_activities.filter(timestamp__date=filter_date)
        user_logs = user_logs.filter(timestamp__date=filter_date)
    
    # Apply search filter
    if search_query:
        from django.db.models import Q
        assessments = assessments.filter(
            Q(barangay__icontains=search_query) |
            Q(flood_risk_code__icontains=search_query) |
            Q(flood_risk_description__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
        reports = reports.filter(
            Q(barangay__icontains=search_query) |
            Q(flood_risk_code__icontains=search_query) |
            Q(flood_risk_label__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
        certificates = certificates.filter(
            Q(establishment_name__icontains=search_query) |
            Q(owner_name__icontains=search_query) |
            Q(barangay__icontains=search_query) |
            Q(location__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
        flood_activities = flood_activities.filter(
            Q(event_type__icontains=search_query) |
            Q(affected_barangays__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
        user_logs = user_logs.filter(
            Q(action__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
    
    # Export based on type and activity
    if export_type == 'pdf':
        if activity_type == 'assessments':
            headers, data = export_utils.prepare_assessments_data(assessments)
            return export_utils.export_to_pdf('Flood Risk Assessment Records', headers, data, 'assessments', filter_info=filter_info, summary_stats={'total': len(data), 'filtered': bool(filter_user or filter_date)})
        elif activity_type == 'reports':
            headers, data = export_utils.prepare_reports_data(reports)
            return export_utils.export_to_pdf('Flood Risk Reports', headers, data, 'reports', filter_info=filter_info, summary_stats={'total': len(data), 'filtered': bool(filter_user or filter_date)})
        elif activity_type == 'certificates':
            headers, data = export_utils.prepare_certificates_data(certificates)
            return export_utils.export_to_pdf('Flood Risk Certificates', headers, data, 'certificates', filter_info=filter_info, summary_stats={'total': len(data), 'filtered': bool(filter_user or filter_date)})
        elif activity_type == 'flood-records':
            headers, data = export_utils.prepare_flood_activities_data(flood_activities)
            return export_utils.export_to_pdf('Flood Activity Records', headers, data, 'flood_activities', filter_info=filter_info, summary_stats={'total': len(data), 'filtered': bool(filter_user or filter_date)})
        elif activity_type == 'user-logs':
            headers, data = export_utils.prepare_user_logs_data(user_logs)
            return export_utils.export_to_pdf('User Activity Logs', headers, data, 'user_logs', filter_info=filter_info, summary_stats={'total': len(data), 'filtered': bool(filter_user or filter_date)})
    else:  # CSV
        if activity_type == 'assessments':
            return export_utils.export_assessments_to_csv(assessments, filter_info=filter_info)
        elif activity_type == 'reports':
            return export_utils.export_reports_to_csv(reports, filter_info=filter_info)
        elif activity_type == 'certificates':
            return export_utils.export_certificates_to_csv(certificates, filter_info=filter_info)
        elif activity_type == 'flood-records':
            return export_utils.export_flood_activities_to_csv(flood_activities, filter_info=filter_info)
        elif activity_type == 'user-logs':
            return export_utils.export_user_logs_to_csv(user_logs, filter_info=filter_info)
    
    # Default fallback
    return export_utils.export_assessments_to_csv(assessments, filter_info=filter_info)