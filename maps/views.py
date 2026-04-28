from django.core.serializers import serialize
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Barangay, FloodSusceptibility, AssessmentRecord, ReportRecord, CertificateRecord, FloodRecordActivity
from users.models import UserLog
from datetime import datetime

try:
    from . import export_utils
except ImportError:
    export_utils = None

@login_required
def error_view(request):
    """Display error message to user"""
    error_title = request.GET.get('title', 'An Error Occurred')
    error_message = request.GET.get('message', 'Something went wrong. Please try again.')
    error_details = request.GET.get('details', '')
    
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
    barangay = request.GET.get('barangay', 'Unknown')
    latitude = request.GET.get('lat', '0.000000')
    longitude = request.GET.get('lon', '0.000000')
    risk_code = request.GET.get('risk', 'Unknown')
    
    # Risk assessment and recommendation mapping
    risk_data = {
        'LF': {
            'label': 'Low Susceptibility; less than 0.5 meters flood height and/or less than 1 day flooding',
            'class': 'risk-low',
            'assessment': 'Low Susceptibility; less than 0.5 meters flood height and/or less than 1 day flooding',
            'recommendation': 'Areas with low susceptibility to floods are likely to experience flood heights of less than 0.5 meters and/or flood duration of less than 1 day. These include low hills and gentle slopes that have sparse to moderate drainage density.\n\nThe implementation of appropriate mitigation measures as deemed necessary by project engineers and LGU building officials is recommended for areas that are susceptible to various flood depths. Site-specific studies including the assessment for other types of hazards should also be conducted to address potential foundation problems.'
        },
        'MF': {
            'label': 'Moderate Susceptibility; 0.5 to 1 meter flood height and/or 1 to 3 days flooding',
            'class': 'risk-moderate',
            'assessment': 'Moderate Susceptibility; 0.5 to 1 meter flood height and/or 1 to 3 days flooding',
            'recommendation': 'Areas with moderate susceptibility to floods are likely to experience flood heights of 0.5 meters up to 1 meter and/or flood duration of 1 to 3 days. These are subject to widespread inundation during prolonged and extensive heavy rainfall or extreme weather conditions. Fluvial terraces, alluvial fans, and infilled valleys are also moderately subjected to flooding.\n\nThe implementation of appropriate mitigation measures as deemed necessary by project engineers and LGU building officials is recommended for areas that are susceptible to various flood depths. Site-specific studies including the assessment for other types of hazards should also be conducted to address potential foundation problems.'
        },
        'HF': {
            'label': 'High Susceptibility; 1 to 2 meters flood height and/or more than 3 days flooding',
            'class': 'risk-high',
            'assessment': 'High Susceptibility; 1 to 2 meters flood height and/or more than 3 days flooding',
            'recommendation': 'Areas with high susceptibility to floods are likely to experience flood heights of 1 meter up to 2 meters and/or flood duration of more than 3 days. Sites including active river channels, abandoned river channels, and areas along riverbanks, are immediately flooded during heavy rains of several hours and are prone to flash floods. These may be considered not suitable for permanent habitation but may be developed for alternative uses subject to the implementation of appropriate mitigation measures after conducting site-specific geotechnical studies as deemed necessary by project engineers and LGU building officials.\n\nThe implementation of appropriate mitigation measures as deemed necessary by project engineers and LGU building officials is recommended for areas that are susceptible to various flood depths. Site-specific studies including the assessment for other types of hazards should also be conducted to address potential foundation problems.'
        },
        'VHF': {
            'label': 'Very High Susceptibility; more than 2 meters flood height and/or more than 3 days flooding',
            'class': 'risk-very-high',
            'assessment': 'Very High Susceptibility; more than 2 meters flood height and/or more than 3 days flooding',
            'recommendation': 'Areas with very high susceptibility to floods are likely to experience flood heights of greater than 2 meters and/or flood duration of more than 3 days. These include active river channels, abandoned river channels, and areas along riverbanks, which are immediately flooded during heavy rains of several hours and are prone to flash floods. These are considered critical geohazard areas and are not suitable for development. It is recommended that these be declared as "No Habitation/No Build Zones" by the LGU, and that affected households/communities be relocated.\n\nThe implementation of appropriate mitigation measures as deemed necessary by project engineers and LGU building officials is recommended for areas that are susceptible to various flood depths. Site-specific studies including the assessment for other types of hazards should also be conducted to address potential foundation problems.'
        }
    }
    
    # Get the appropriate risk data or use default
    current_risk = risk_data.get(risk_code, {
        'label': 'Unknown Risk Level',
        'class': '',
        'assessment': 'No risk data available',
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
    
    context = {
        'barangay': barangay,
        'latitude': latitude,
        'longitude': longitude,
        'risk_code': risk_code,
        'risk_label': current_risk['label'],
        'risk_class': current_risk['class'],
        'assessment_text': current_risk['assessment'],
        'recommendation_text': current_risk['recommendation'],
        'current_date': current_date,
    }
    
    return render(request, 'maps/report.html', context)

@login_required
def certificate_form_view(request):
    # Get parameters from URL
    barangay = request.GET.get('barangay', 'Unknown')
    latitude = request.GET.get('lat', '0.000000')
    longitude = request.GET.get('lon', '0.000000')
    risk_code = request.GET.get('risk', 'Unknown')
    
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
        # Get form data
        establishment_name = request.POST.get('establishment_name', '')
        owner_name = request.POST.get('owner_name', '')
        location = request.POST.get('location', '')
        barangay = request.POST.get('barangay', 'Unknown')
        zone_status = request.POST.get('zone_status', '')
        issue_date = request.POST.get('issue_date', '')
        signatory_name = request.POST.get('signatory_name', '')
        signatory_title = request.POST.get('signatory_title', '')
        signatory_subtitle = request.POST.get('signatory_subtitle', '')
        
        # Get assessment data from hidden fields
        latitude = request.POST.get('latitude', '0.000000')
        longitude = request.POST.get('longitude', '0.000000')
        flood_susceptibility = request.POST.get('flood_susceptibility', 'Unknown')
        risk_code = request.POST.get('risk_code', 'Unknown')
        
        # Get mitigating measures value from hidden field
        mitigating_measures_value = request.POST.get('mitigating_measures_value', 'false')
        
        # Save certificate generation record
        CertificateRecord.objects.create(
            user=request.user,
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
        
        context = {
            'establishment_name': establishment_name,
            'owner_name': owner_name,
            'location': location,
            'barangay': barangay.upper(),
            'flood_susceptibility': flood_susceptibility,
            'zone_status': zone_status,
            'issue_date': issue_date,
            'signatory_name': signatory_name,
            'signatory_title': signatory_title,
            'signatory_subtitle': signatory_subtitle,
            'mitigating_measures_value': mitigating_measures_value,
        }
        
        return render(request, 'maps/certificate.html', context)
    
    # If not POST, redirect to form
    return redirect('map_view')

# New view for saving assessments via AJAX
@login_required
def save_assessment(request):
    from django.http import JsonResponse
    
    if request.method == 'POST':
        barangay = request.POST.get('barangay', 'Unknown')
        latitude = request.POST.get('latitude', '0.000000')
        longitude = request.POST.get('longitude', '0.000000')
        flood_risk_code = request.POST.get('flood_risk_code', 'Unknown')
        
        # Map risk codes to descriptions
        risk_descriptions = {
            'LF': 'Low Flood Susceptibility',
            'MF': 'Moderate Flood Susceptibility',
            'HF': 'High Flood Susceptibility',
            'VHF': 'Very High Flood Susceptibility'
        }
        
        flood_risk_description = risk_descriptions.get(flood_risk_code, 'Unknown')
        
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