import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 10000,
});

export const getStats = () =>
  api.get('/events/stats').then(r => r.data);

export const getEvents = (params) =>
  api.get('/events', { params }).then(r => r.data);

export const getEvent = (eventId) =>
  api.get(`/events/${eventId}`).then(r => r.data);

export const retryEvent = (eventId) =>
  api.post(`/events/${eventId}/retry`).then(r => r.data);