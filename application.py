import logging
import os
import random
import string
import threading
from datetime import datetime
from typing import List
from utils import verify_signature

import dotenv
import stripe
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request, jsonify, Response
from flask_basicauth import BasicAuth
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity

from src import bot_state
from src.agents import CodyCareAgent
from src.analytics.analytics_scheduler import process_conversations
from src.ats.scheduler import run_ats_on_recent_convs
from src.bot import Bot
from src.followup.followup_care import FollowupCare
from src.followup.followup_care_scheduler import process_followup_care
from src.rx.doctor_service import DoctorService
from src.rx.doctor_service_state import DoctorServiceOfferEvent
from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup
from src.user.users_account import update_user_verified
from src.utils import refresh_view, MongoDBClient, base_url

dotenv.load_dotenv()

logging.getLogger('flask_cors').level = logging.WARN

application = Flask(__name__)

cors = CORS(application, resources={r"/*": {"origins": ["https://cody.md",
                                                        "https://www.cody.md",
                                                        "https://staging.cody.md",
                                                        "https://codymd.app",
                                                        "https://cody-md.com",
                                                        "https://preprod.cody.md",
                                                        "http://localhost:3000",
                                                        "http://localhost:3001",
                                                        r"https?://([\w-]+\.)?([\w-]+\.)?amplifyapp\.com"
                                                        ]
                                            }})

# TODO Move to a secret file
application.config['JWT_SECRET_KEY'] = 'secret'
jwt = JWTManager(application)

# TODO Move to a secret file
application.config['BASIC_AUTH_USERNAME'] = 'admin'
application.config['BASIC_AUTH_PASSWORD'] = 'adminCody@123'

basic_auth = BasicAuth(application)

valid_credentials_grading_endpoint = {
    'admin': 'adminCody@123'
}

valid_credentials_token_endpoint = {
    'cody_frontend': 'frontend@123',
    'social_app': 'social@123'
}

scheduler = BackgroundScheduler()
scheduler.start()


@application.route('/new_token', methods=['GET'])
def new_token():
    auth = request.authorization

    if (not auth or auth.username not in valid_credentials_token_endpoint
            or valid_credentials_token_endpoint[auth.username] != auth.password):
        logging.warning(f'Unauthorized access to grading endpoint by {auth}')
        return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

    current_user = request.args.get('session_id')

    if not current_user:
        characters = string.ascii_letters + string.digits
        current_user = ''.join(random.choice(characters) for _ in range(50))  # Create random user id
    logging.info(f'New token requested for user: {current_user}')
    return jsonify({'access_token': create_access_token(identity=current_user, expires_delta=False)}), 200


@application.route('/init', methods=['GET'])
@jwt_required()
def init():
    current_user = get_jwt_identity()

    logging.info(f'Initializing bot for user: {current_user}')

    profile = {}

    if request.args.get('name'):
        profile['name'] = request.args.get('name')

    if request.args.get('character'):
        profile['character'] = request.args.get('character')

    if request.args.get('followup'):
        profile['followup'] = request.args.get('followup')

    if request.args.get('email'):
        profile['email'] = request.args.get('email')

    ip_address = ''
    # Get the remote IP address from the request object
    if 'X-Forwarded-For' in request.headers:
        # The X-Forwarded-For header can contain a comma-separated list of IPs
        # The actual client IP is typically the first one in the list
        ip_address = request.headers['X-Forwarded-For'].split(',')[0].strip()

    bot = Bot(username=current_user, profile=profile, ip_address=ip_address)

    conv_hist: List[dict] = bot.get_conv_hist()

    return jsonify({
        'conv_hist': conv_hist,
        'current_user': current_user,
        'version': bot.state.version,
        'chief_complaint': bot.state.chief_complaint,
        'specialist': bot.state.specialist.inventory_name,
        'subSpecialty': bot.state.subSpecialty.inventory_name,
    }), 200


def profile_bot(bot, profile):
    name = profile.get('name', None)

    if name is not None:
        bot.state.patient_name = name


@application.route('/ask', methods=['POST'])
@jwt_required()
def ask():
    # Get the user input
    input = request.get_json().get('input')

    ip_address = ''
    # Get the remote IP address from the request object
    if 'X-Forwarded-For' in request.headers:
        # The X-Forwarded-For header can contain a comma-separated list of IPs
        # The actual client IP is typically the first one in the list
        ip_address = request.headers['X-Forwarded-For'].split(',')[0].strip()

    current_user = get_jwt_identity()

    bot = Bot(username=current_user,
              profile=request.get_json().get('profile', {}),
              ip_address=ip_address)

    if not input and bot.state.current_agent_name != CodyCareAgent.name:
        return jsonify({'error': 'Input is required'}), 400

    return Response(bot.ask(input), mimetype="text/event-stream")


@application.route('/admin/grade/<userid>', methods=['GET'])
def grading_history(userid: str):
    auth = request.authorization
    if (not auth or auth.username not in valid_credentials_grading_endpoint
            or valid_credentials_grading_endpoint[auth.username] != auth.password):
        logging.warning(f'Unauthorized access to grading endpoint by {auth}')
        return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

    bot = Bot(username=userid)
    conv_hist: List[dict] = bot.get_conv_hist()

    return jsonify({
        'conv_hist': conv_hist,
        'patient_name': bot.state.patient_name,
    }), 200


@application.route('/admin/supported/specialist', methods=['GET'])
def supported_specialist():
    auth = request.authorization
    if (not auth or auth.username not in valid_credentials_grading_endpoint
            or valid_credentials_grading_endpoint[auth.username] != auth.password):
        logging.warning(f'Unauthorized access to grading endpoint by {auth}')
        return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

    specialist_mapping = dict()
    for sp in Specialist:
        specialist_mapping[sp.inventory_name] = [sub_sp.inventory_name for sub_sp in
                                                 SubSpecialtyDxGroup.valid_sub_speciality(sp)]

    return jsonify(specialist_mapping), 200


@application.route('/admin/mapping', methods=['GET'])
def get_llm_mapping():
    auth = request.authorization
    if (not auth or auth.username not in valid_credentials_grading_endpoint
            or valid_credentials_grading_endpoint[auth.username] != auth.password):
        logging.warning(f'Unauthorized access to grading endpoint by {auth}')
        return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

    records = MongoDBClient.get_dx_mapping().find({}).sort('created', -1)

    response = list[dict]()

    for record in records:
        source_ = {
            'diagnosis': record['diagnosis'],
            'dx_group': record['dx_group'],
            'specialist': record['specialist'],
            'created': record['created'],
            'source': record['source']
        }

        if record.get('bookmark'):
            source_['bookmark'] = record['bookmark']

        response.append(source_)

    return jsonify(response), 200


@application.route('/admin/mapping/update', methods=['POST'])
def update_llm_mapping():
    auth = request.authorization
    if (not auth or auth.username not in valid_credentials_grading_endpoint
            or valid_credentials_grading_endpoint[auth.username] != auth.password):
        logging.warning(f'Unauthorized access to grading endpoint by {auth}')
        return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

    data = request.get_json()

    if data is None:
        return jsonify({'error': 'Input is required'}), 400

    update_dict = {
        'dx_group': data['dx_group'],
        'specialist': data['specialist'],
        'updated': datetime.now().isoformat(),
    }

    # we don't want to change source if bookmark is updated
    if data.get('bookmark') is not None:
        update_dict['bookmark'] = data['bookmark']
    else:
        update_dict['source'] = 'admin'

    MongoDBClient.get_dx_mapping().update_one(filter={'diagnosis': data['diagnosis']},
                                              update={'$set': update_dict},
                                              upsert=True)

    return jsonify({'message': 'success'}), 200


@application.route('/ask/meta', methods=['GET'])
@jwt_required()
def convo_meta():
    current_user = get_jwt_identity()

    bot = Bot(username=current_user)

    meta_ = {
        'serving_agent_name': bot.state.current_agent_name,
        'chief_complaint': bot.state.chief_complaint,
        'diagnosis_list': bot.state.diagnosis_list,
        'cc_sub_speciality': bot.state.subSpecialty.inventory_name,
        'cc_specialist': bot.state.specialist.inventory_name,
        'dx_group_list': [dx_group.inventory_name for dx_group in bot.state.dx_group_list],
        'dx_specialist_list': [dx_specialist.inventory_name for dx_specialist in bot.state.dx_specialist_list],
        'concierge_option': bot.state.concierge_option
    }

    is_payment_eligible, is_verification_eligible, offer_id = DoctorService.payment_verification_status(current_user,
                                                                                                        bot.state.current_agent_name)

    if is_payment_eligible:
        meta_['initiate_payment'] = is_payment_eligible
        meta_['offer_id'] = offer_id
    elif is_verification_eligible:
        meta_['initiate_verification'] = is_verification_eligible
        meta_['offer_id'] = offer_id

    return jsonify(meta_), 200


@application.route('/stats', methods=['GET'])
@jwt_required()
def stats():
    stats_data = MongoDBClient.get_stats().find_one({})

    return jsonify({
        'dxCount': stats_data['dxCount'],
    }), 200


@application.route('/care/optout', methods=['GET'])
@jwt_required()
def care_opt_out():
    conv_id = get_jwt_identity()

    count = FollowupCare.opt_out(conv_id)

    if count == 0:
        return jsonify({'error': 'Not eligible for opt out'}), 400

    return jsonify({'message': 'Opted out successfully'}), 200


scheduler.add_job(refresh_view, 'interval', hours=6, max_instances=1)
scheduler.add_job(run_ats_on_recent_convs, 'interval', hours=1, max_instances=1)
scheduler.add_job(process_followup_care, 'interval', hours=1, max_instances=1)
scheduler.add_job(process_conversations, 'interval', hours=1, max_instances=1)


@application.route('/', methods=['GET'])
def index():
    return f"Welcome to Cody! v{bot_state.VERSION}"


@application.route('/gsc/webhook', methods=['POST'])
def site_control_webhook():
    user_agent = request.headers.get('User-Agent')

    if 'Getsitecontrol WebHook' not in user_agent:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.form

    if data:
        convo_id = data.get('convo_id')
        email = data.get('user_email')
        gsc_cc_code = data.get('cc_code')
        gsc_city = data.get('cc_city')
        nps = data.get('nps')
        environment = data.get('environment')

        if convo_id:
            logging.info(f'GSC Webhook received for convo_id: {convo_id}')

            if environment == 'production':
                MongoDBClient.get_convo_analytics().update_one(
                    filter={'convo_id': convo_id},
                    update={'$set': {
                        'convo_id': convo_id,
                        'user_email': email,
                        'gsc_cc_code': gsc_cc_code,
                        'gsc_city': gsc_city,
                        'nps': nps,
                        'updated': datetime.now().isoformat(),

                    },
                        '$setOnInsert': {
                            'created': datetime.now().isoformat()
                        }
                    },
                    upsert=True
                )
            else:
                logging.info(
                    f'GSC Webhook received for convo_id: {convo_id} in {environment} environment. Skipping analytics update.')

    return jsonify({'message': 'success'}), 200


@application.route('/create-checkout-session', methods=['POST'])
@jwt_required()
def create_checkout_session():
    convo_id = get_jwt_identity()
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

    service = DoctorService.latest_event(convo_id)

    if service.event != DoctorServiceOfferEvent.OFFER_ACCEPTED:
        return jsonify({'error': 'No active service for this conversation'}), 400

    try:
        session = stripe.checkout.Session.create(
            ui_mode='embedded',
            customer_email=service.user_id,
            payment_method_types=['card'],
            payment_intent_data={
                'capture_method': 'manual',
                'metadata': {
                    'convo_id': convo_id,
                    'offer_id': service.offer_id,
                },
            },
            line_items=[
                {
                    # Provide the exact Price ID (for example, pr_1234) of the product you want to sell
                    'price': os.getenv('STRIPE_PRICE_ID'),
                    'quantity': 1,
                },
            ],
            mode='payment',
            return_url=base_url() + f'convo/{convo_id}?session_id=' + '{CHECKOUT_SESSION_ID}',
        )
    except Exception as e:
        logging.error(f'Error creating checkout session for convo_id: {convo_id}', exc_info=e)
        return jsonify({'error': str(e)}), 400

    return jsonify(clientSecret=session.client_secret, sessionId=session.id), 200


@application.route('/session-status', methods=['GET'])
@jwt_required()
def session_status():
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
    session = stripe.checkout.Session.retrieve(request.args.get('session_id'))

    if session.customer_details is None:
        return jsonify(status=session.status)

    return jsonify(status=session.status, customer_email=session.customer_details.email)


@application.route('/akute-webhook', methods=['POST'])
def akute_webhook():
    webhook_secret = os.getenv('AKUTE_WEBHOOK_SECRET')
    header = request.headers.get('x-akute-signature')
    if verify_signature(header, request.get_data(as_text=True), webhook_secret):
        logging.info("Signature is valid!")
    else:
        return jsonify({'error': 'Unauthorized'}), 401
    akute_task: dict = request.json

    # Proceed only if task is completed
    if akute_task.get('status') != 'complete':
        return jsonify({'message': 'Task not completed'}), 200

    # Get the task ID
    task_id = akute_task.get('id')

    # Fetch event from the task ID
    event = DoctorService.get_event_for_task_id(task_id)

    # If no event found, return
    if event is None:
        logging.info(f'No event found for task {task_id}')
        return jsonify({'message': f'No event found for task {task_id}'}), 200

    logging.info(f'Processing Akute task for event: {event.event}')

    DoctorService.capture(event.offer_id, event.convo_id, event.user_id, DoctorServiceOfferEvent.EHR_TASK_DONE, {
        'ehr_task': akute_task
    })

    threading.Thread(target=DoctorService.process_for_certified_plan,
                     args=(event.offer_id,)).start()

    return jsonify({'message': 'success'}), 200


@application.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv('STRIPE_ENDPOINT_SECRET')
        )
    except ValueError as e:
        # Invalid payload
        logging.error(f'Invalid payload: {e}')
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logging.error(f'Invalid signature: {e}')
        return jsonify({'error': 'Invalid signature'}), 400

    # Handle the event
    if event['type'] == 'charge.succeeded':
        session = event['data']['object']

        convo_id = session.metadata.get('convo_id')
        offer_id = session.metadata.get('offer_id')

        service = DoctorService.latest_event(convo_id)

        if service.event != DoctorServiceOfferEvent.OFFER_ACCEPTED:
            logging.error(f'Invalid service event for convo_id: {convo_id}')
            return jsonify({'error': 'Invalid service event'}), 400

        if offer_id != service.offer_id:
            logging.error(f'Offer ID mismatch for convo_id: {convo_id}')
            return jsonify({'error': 'Offer ID mismatch'}), 400

        DoctorService.capture(offer_id, convo_id, service.user_id, DoctorServiceOfferEvent.OFFER_PAYMENT_DONE, {
            'payment': {
                'id': session.payment_intent,
                'receipt_url': session.receipt_url,
            }
        })

    return jsonify({'message': 'success'}), 200


@application.route('/veriff-webhook', methods=['POST'])
def veriff_webhook():
    """
    Veriff Webhook for user verification
    This is called by veriff when verification outcome is available
    :return:
    """

    key = request.headers.get('x-auth-client')

    if key != os.getenv('VERIFF_WEBHOOK_KEY'):
        logging.error(f'Unauthorized access to Veriff Webhook by {key}')
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()

    if data and data.get('status') == 'success':
        logging.info('Veriff Webhook received for decision: success')

        offer_id = data.get('vendorData')
        verification_data = data.get('data', {}).get('verification')

        if verification_data:

            service = DoctorService.latest_event_by_offer(offer_id)

            if service.event not in [DoctorServiceOfferEvent.VERIFY_USER,
                                     DoctorServiceOfferEvent.USER_VERIFICATION_FAILED]:
                logging.error(f'Invalid service event for offer_id: {offer_id}')
                return jsonify({'error': 'Invalid service event'}), 200

            decision = verification_data.get('decision')

            # https://developers.veriff.com/#session-status
            if decision == 'approved':
                update_user_verified(service.user_id)

                DoctorService.capture(offer_id, service.convo_id, service.user_id,
                                      DoctorServiceOfferEvent.USER_VERIFIED, {
                                          'verification': verification_data
                                      })

            else:
                DoctorService.capture(offer_id, service.convo_id, service.user_id,
                                      DoctorServiceOfferEvent.USER_VERIFICATION_FAILED, {
                                          'verification': verification_data
                                      })

    return jsonify({'message': 'success'}), 200


@application.route('/admin/process/offer/<offer>', methods=['POST'])
def process_offer(offer: str):
    auth = request.authorization
    if (not auth or auth.username not in valid_credentials_grading_endpoint
            or valid_credentials_grading_endpoint[auth.username] != auth.password):
        logging.warning(f'Unauthorized access to process offer endpoint by {auth}')
        return Response('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

    latest_event = DoctorService.latest_event_by_offer(offer)

    if latest_event.event == DoctorServiceOfferEvent.EHR_TASK_DONE:
        DoctorService.process_for_certified_plan(offer)
        return jsonify({'message': 'success'}), 200
    elif latest_event.event == DoctorServiceOfferEvent.SEND_TO_EHR:
        DoctorService.process_for_ehr(offer)
        return jsonify({'message': 'success'}), 200

    return jsonify({'error': f'Ineligible for processing. Latest event: {latest_event.event}'}), 400


if __name__ == '__main__':
    # Remove handlers in logger for debug runs
    logging.getLogger().removeHandler(logging.getLogger().handlers[0])
    application.run(debug=True, threaded=True)
