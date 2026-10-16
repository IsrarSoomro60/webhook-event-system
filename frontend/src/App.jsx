import { useEffect, useState } from 'react';
import { getStats, getEvents, retryEvent } from './api';
import EventDetailModal from './EventDetailModal';

export default function App() {
  const [stats, setStats] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [retryingId, setRetryingId] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsData, eventsData] = await Promise.all([
        getStats(),
        getEvents({
          status: statusFilter || undefined,
          search: search || undefined,
        }),
      ]);
      setStats(statsData);
      setEvents(eventsData.results || []);
    } catch (err) {
      setError('Failed to load data. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [statusFilter, search]);

  const handleRetry = async (eventId) => {
    setRetryingId(eventId);
    try {
      await retryEvent(eventId);
      await load();
    } catch (err) {
      alert(err.response?.data?.error || 'Retry failed');
    } finally {
      setRetryingId(null);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold">Webhook Monitoring Dashboard</h1>
          <button
            onClick={load}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
          >
            Refresh
          </button>
        </div>

        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <StatCard label="Total" value={stats.total} color="gray" />
            <StatCard label="Processed" value={stats.processed} color="green" />
            <StatCard label="Pending" value={stats.pending} color="yellow" />
            <StatCard label="Processing" value={stats.processing} color="blue" />
            <StatCard label="Failed" value={stats.failed} color="red" />
          </div>
        )}

        <div className="flex flex-wrap gap-2 mb-4">
          <input
            type="text"
            placeholder="Search by event ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="border rounded px-3 py-2 flex-1 min-w-[200px]"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="border rounded px-3 py-2"
          >
            <option value="">All statuses</option>
            <option value="RECEIVED">Received</option>
            <option value="PENDING">Pending</option>
            <option value="PROCESSING">Processing</option>
            <option value="PROCESSED">Processed</option>
            <option value="FAILED">Failed</option>
            <option value="PERMANENTLY_FAILED">Permanently Failed</option>
          </select>
        </div>

        {loading && (
          <div className="text-center py-8 text-gray-500">Loading...</div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded">
            {error}
          </div>
        )}

        {!loading && !error && events.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            No events found.
          </div>
        )}

        {!loading && !error && events.length > 0 && (
          <div className="bg-white rounded shadow overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 text-left">
                <tr>
                  <th className="p-3">Event ID</th>
                  <th className="p-3">Type</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Attempts</th>
                  <th className="p-3">Received At</th>
                  <th className="p-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => (
                  <tr key={ev.event_id} className="border-t hover:bg-gray-50">
                    <td
                      className="p-3 text-blue-600 cursor-pointer font-mono text-xs"
                      onClick={() => setSelectedEventId(ev.event_id)}
                    >
                      {ev.event_id}
                    </td>
                    <td className="p-3 font-mono text-xs">{ev.event_type}</td>
                    <td className="p-3">
                      <StatusBadge status={ev.status} />
                    </td>
                    <td className="p-3">{ev.attempt_count}</td>
                    <td className="p-3 text-xs">
                      {new Date(ev.received_at).toLocaleString()}
                    </td>
                    <td className="p-3">
                      {(ev.status === 'FAILED' ||
                        ev.status === 'PERMANENTLY_FAILED') && (
                        <button
                          onClick={() => handleRetry(ev.event_id)}
                          disabled={retryingId === ev.event_id}
                          className="bg-yellow-500 hover:bg-yellow-600 disabled:opacity-50 text-white px-3 py-1 rounded text-xs"
                        >
                          {retryingId === ev.event_id ? 'Retrying...' : 'Retry'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedEventId && (
        <EventDetailModal
          eventId={selectedEventId}
          onClose={() => setSelectedEventId(null)}
        />
      )}
    </div>
  );
}

function StatCard({ label, value, color }) {
  const colors = {
    gray: 'bg-gray-50 border-gray-200',
    green: 'bg-green-50 border-green-200',
    yellow: 'bg-yellow-50 border-yellow-200',
    blue: 'bg-blue-50 border-blue-200',
    red: 'bg-red-50 border-red-200',
  };
  return (
    <div className={`rounded border p-4 ${colors[color]}`}>
      <div className="text-xs text-gray-600 uppercase">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}

function StatusBadge({ status }) {
  const styles = {
    RECEIVED: 'bg-gray-100 text-gray-700',
    PENDING: 'bg-yellow-100 text-yellow-700',
    PROCESSING: 'bg-blue-100 text-blue-700',
    PROCESSED: 'bg-green-100 text-green-700',
    FAILED: 'bg-red-100 text-red-700',
    PERMANENTLY_FAILED: 'bg-red-200 text-red-900',
  };
  return (
    <span className={`px-2 py-1 rounded text-xs ${styles[status] || 'bg-gray-100'}`}>
      {status}
    </span>
  );
}