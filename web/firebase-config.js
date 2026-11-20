/* Konfiguracja web Firebase.
   Te wartosci sa publiczne z zalozenia - trafiaja do kodu strony, ktory kazdy
   moze przeczytac. Dostepu pilnuja reguly Firestore (firebase/firestore.rules),
   nie ukrywanie tego pliku. Tajny jest wylacznie klucz konta serwisowego,
   ktory zyje w sekretach repozytorium i nigdy tutaj nie trafia. */
export const FIREBASE = {
  apiKey: "AIzaSyCCniUzo1GoHNpDUHAuClBxgLgBBDGn3i4",
  authDomain: "momentum-invest-ca57f.firebaseapp.com",
  projectId: "momentum-invest-ca57f",
  storageBucket: "momentum-invest-ca57f.firebasestorage.app",
  messagingSenderId: "91237204146",
  appId: "1:91237204146:web:6c1c365f2014c6ae2949ab",
};
