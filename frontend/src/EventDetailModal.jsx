import { useEffect, useState } from 'react';
import { getEvent } from './api';

export default function EventDetailModal({ eventId, onClose }) {
  const [event, setEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getEvent(eventId)
      .then(setEvent)
      .catch(() => setError('Failed to load event details'))
      .finally(() => setLoading(false));
  }, [eventId]);

  if (!event) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg p-6 max-w-lg w-full">
          {loading && <p>Loading...</p>}
          {error && <p className="text-red-600">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg max-w-2xl w-full p-6 max-h-[90vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold break-all">{event.event_id}</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-800 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        <dl className="grid grid-cols-2 gap-3 text-sm mb-4">
          <div>
            <dt className="text-gray-500">Type</dt>
            <dd className="font-mono">{event.event_type}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Status</dt>
            <dd>{event.status}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Attempts</dt>
            <dd>{event.attempt_count}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Received At</dt>
            <dd>{new Date(event.received_at).toLocaleString()}</dd>
          </div>
          {event.processed_at && (
            <div>
              <dt className="text-gray-500">Processed At</dt>
              <dd>{new Date(event.processed_at).toLocaleString()}</dd>
            </div>
          )}
        </dl>

        {event.last_error && (
          <div className="mb-4">
            <div className="text-sm text-gray-500 mb-1">Last Error</div>
            <div className="bg-red-50 text-red-700 p-2 rounded text-sm font-mono break-all">
              {event.last_error}
            </div>
          </div>
        )}

        {event.attempts && event.attempts.length > 0 && (
          <div className="mb-4">
            <div className="text-sm text-gray-500 mb-2">Processing History</div>
            <div className="space-y-2">
              {event.attempts.map((attempt) => (
                <div
                  key={attempt.attempt_number}
                  className="border rounded p-2 text-sm"
                >
                  <div className="flex justify-between">
                    <span className="font-semibold">
                      Attempt #{attempt.attempt_number}
                    </span>
                    <span
                      className={
                        attempt.status === 'SUCCESS'
                          ? 'text-green-600'
                          : 'text-red-600'
                      }
                    >
                      {attempt.status}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500">
                    Started: {new Date(attempt.started_at).toLocaleString()}
                    {attempt.finished_at &&
                      ` → Finished: ${new Date(attempt.finished_at).toLocaleString()}`}
                  </div>
                  {attempt.error && (
                    <div className="text-xs text-red-600 mt-1 font-mono break-all">
                      {attempt.error}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <div className="text-sm text-gray-500 mb-1">Original Payload</div>
          <pre className="bg-gray-100 p-3 rounded text-xs overflow-auto">
            {JSON.stringify(event.payload, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}