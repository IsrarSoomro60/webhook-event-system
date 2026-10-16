import time


def process_event(event):

    payload = event.payload

    if event.event_type == 'user.created':
        
        time.sleep(0.5)
        return True

    if event.event_type == 'payment.completed':
        
        if payload.get('simulate_failure') is True:
            raise Exception('Simulated payment processing failure')
        time.sleep(0.5)
        return True

    raise Exception(f'No handler for event type: {event.event_type}')