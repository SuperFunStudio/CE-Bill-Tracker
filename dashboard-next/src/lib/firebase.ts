// Firebase web app config — these values are PUBLIC by design (they identify the project, they are
// not secrets). Access is controlled by Firebase Auth + backend ID-token verification, not by hiding
// this config. Retrieved via `firebase apps:sdkconfig WEB`. See gating-and-monetization-plan.
import { initializeApp, getApps, getApp, type FirebaseApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider, type Auth } from 'firebase/auth';

const firebaseConfig = {
  apiKey: 'AIzaSyDEhG3X9ufgPu1ffP190L9XLhJDSeDRs94',
  authDomain: 'ce-bill-tracker.firebaseapp.com',
  projectId: 'ce-bill-tracker',
  storageBucket: 'ce-bill-tracker.firebasestorage.app',
  messagingSenderId: '36712717703',
  appId: '1:36712717703:web:fcf419d5992f72e4a00722',
  measurementId: 'G-S858LD2MMN',
};

export const firebaseApp: FirebaseApp = getApps().length ? getApp() : initializeApp(firebaseConfig);
export const auth: Auth = getAuth(firebaseApp);
export const googleProvider = new GoogleAuthProvider();
