#Django
from django.shortcuts import render, HttpResponseRedirect, redirect
from django.core.urlresolvers import reverse
from django.contrib.auth import logout
from django.contrib import messages

#Project
from .models import Doctor, Patient
from .forms import PatientForm, DemographicForm

#Python
import datetime, time
import requests, pytz

from drchrono.settings import SOCIAL_AUTH_DRCHRONO_KEY, SOCIAL_AUTH_DRCHRONO_SECRET


def index(request):
    """Sign In"""

    return render(request, 'index.html')


def authorize(request):
    """User authorizes application"""

    base_url = 'https://drchrono.com/o/authorize/'
    redirect_uri = 'http://localhost:8000/login'
    client_id = '2xMAgUko6q02uM8IDnWiNynNwqbhuc7dpgKMxHmE'
    scope = 'patients:read user:read user:write calendar:read calendar:write clinical:read clinical:write'
    url = base_url + "?redirect_uri={}&response_type=code&client_id={}&scope={}".format(redirect_uri, client_id, scope)

    return HttpResponseRedirect(url)


def drchrono_login(request):
    """Drchrono authorization & token exchange"""

    response = requests.post('https://drchrono.com/o/token/', data={
        'code': request.GET['code'],
        'grant_type': 'authorization_code',
        'redirect_uri': 'http://localhost:8000/login',
        'client_id': SOCIAL_AUTH_DRCHRONO_KEY,
        'client_secret': SOCIAL_AUTH_DRCHRONO_SECRET,
    })

    response.raise_for_status()
    data = response.json()

    # Saves these in database associated with the user
    access_token = data['access_token']
    refresh_token = data['refresh_token']
    expires_timestamp = datetime.datetime.now(pytz.utc) + datetime.timedelta(seconds=data['expires_in'])

    try:
        current_user = Doctor.objects.get(user=request.user.id)

        if current_user.expires_timestamp < unicode(datetime.date.today()):
            current_user.access_token = access_token
            current_user.refresh_token = refresh_token
            current_user.expires_timestamp = expires_timestamp
            current_user.save()

    except Doctor.DoesNotExist:
        user = Doctor(
            first_name='John', last_name='Smith', user=1, access_token=access_token, refresh_token=refresh_token,
            expires_timestamp=expires_timestamp
        )
        user.save()

    return HttpResponseRedirect(reverse('home'))


def home(request):
    """Doctor can pick to view appointment list or patient check in"""

    return render(request, 'home.html')


def check_in(request):
    """Patient Check-in"""

    #storing some patient data in db
    user = Doctor.objects.get(user=request.user)

    headers = {
        'Authorization': 'Bearer %s' % user.access_token,
    }

    patients_url = 'https://drchrono.com/api/patients'

    data = requests.get(patients_url, headers=headers).json()

    for data in data['results']:
        if Patient.objects.filter(patient_id=data['id']).exists():
            pass
        else:
            patient = Patient(patient_id=data['id'], first_name=data['first_name'], middle_name=data['middle_name'],
                              last_name=data['last_name'], date_of_birth=data['date_of_birth'], gender=data['gender'],
                              address=data['address'], city=data['city'], state=data['state'], zip_code=data['zip_code'],
                              cell_phone=data['cell_phone'], email=data['email'], ethnicity=data['ethnicity'],
                              preferred_language=data['preferred_language'], race=data['race'],
                              social_security_number=data['social_security_number'],
                              emergency_contact_name=data['emergency_contact_name'],
                              emergency_contact_phone=data['emergency_contact_phone'],
                              emergency_contact_relation=data['emergency_contact_relation'],
                              )
            patient.save()

    form = PatientForm()
    return render(request, 'check_in.html', {'form': form})


def patient_demographic(request):
    """Patient chart that gets updated by patient on check in"""

    if request.method == "POST":
        form = PatientForm(request.POST)

        #if data is valid, query from what is in db, if not present then add new patient
        if form.is_valid():
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            date_of_birth = form.cleaned_data['date_of_birth']

            patient = Patient.objects.filter(first_name=first_name, last_name=last_name, date_of_birth=date_of_birth)

            #retrieve patient's data to display on the form and have the patient update their info
            if patient.exists():
                form = DemographicForm(instance=patient[0])
                return render(request, 'demographic.html', {'form': form})
            else:
                patient = Patient.objects.create(first_name=first_name, last_name=last_name, date_of_birth=date_of_birth)
                form = DemographicForm(instance=patient)
                return render(request, 'demographic.html', {'form': form})
        else:
            messages.error(request, "Error: Please enter your information.")

            return HttpResponseRedirect(reverse('check_in'))

    form = DemographicForm()

    return render(request, 'demographic.html', {'form': form})


def checked_in(request):
    """Patient completed check in."""

    if request.method == "POST":
        patient = Patient.objects.get(first_name=request.POST['first_name'], last_name=request.POST['last_name'],
                                      date_of_birth=request.POST['date_of_birth'])
        form = DemographicForm(request.POST, instance=patient)

        if form.is_valid():
            patient.appointment_status = "Arrived"
            today = datetime.datetime.today()
            patient.arrived_time = utc_to_pacific(today).strftime("%H:%M:%S %P")
            form.save()

    doc = Doctor.objects.get(user=request.user)

    return render(request, 'checked_in.html', {'doc': doc})


def utc_to_pacific(today):
    """Convert UTC datetime to Pacific (Daylight savings aware)"""

    utc = pytz.timezone('UTC')
    aware_date = utc.localize(today)
    pacific = pytz.timezone('US/Pacific')
    pacific_datetime = aware_date.astimezone(pacific)

    return pacific_datetime


def appointments(request):
    """Lists all of today's appointments."""

    user = Doctor.objects.get(user=request.user)

    headers = {
        'Authorization': 'Bearer %s' % user.access_token,
    }

    data = {
        'doctor': 125656,
        'duration': 30,
        'office': 133390,
        'exam_room': 1,
    }

    appointments_url = 'https://drchrono.com/api/appointments'

    today = datetime.datetime.today()
    data = requests.get(appointments_url, params={'data': data, 'date': utc_to_pacific(today).strftime('%Y-%m-%d')},
                        headers=headers).json()
    appointment_info = data['results']

    patients_and_appointments = []

    for appointment in appointment_info:
        patient = Patient.objects.filter(patient_id=appointment['patient'])
        if len(patient.values()) != 0:
            each_patient = patient.values()[0]
            combined_dict = dict(each_patient.items() + appointment.items())
            patients_and_appointments.append(combined_dict)

    return render(request, 'appointment.html', {'patients_and_appointments': patients_and_appointments})


# def average_wait_time(wait_times):
#     """Display average wait time for all patients"""

    # convert wait time to seconds
    # calculate average and convert back to H:M:S format


def drchrono_logout(request):
    """Log out"""

    logout(request)
    return HttpResponseRedirect(reverse('index'))
