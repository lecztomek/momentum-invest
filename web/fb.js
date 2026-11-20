/* Cienka warstwa nad Firebase: logowanie Google i dostep do Firestore.
   Strona ma dzialac takze bez bazy - dane publiczne ida z plikow JSON w repo,
   wiec kazda operacja tutaj jest opcjonalna i jej awaria nie moze zatrzymac
   renderowania. */
import { initializeApp } from "https://www.gstatic.com/firebasejs/11.3.0/firebase-app.js";
import {
  getAuth, GoogleAuthProvider, signInWithPopup, signOut, onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/11.3.0/firebase-auth.js";
import {
  getFirestore, doc, getDoc, setDoc, deleteDoc, collection, getDocs,
} from "https://www.gstatic.com/firebasejs/11.3.0/firebase-firestore.js";
import { FIREBASE } from "./firebase-config.js";

const app = initializeApp(FIREBASE);
export const auth = getAuth(app);
const db = getFirestore(app);

export const zalogujGoogle = () => signInWithPopup(auth, new GoogleAuthProvider());
export const wyloguj = () => signOut(auth);
export const naZmianeKonta = (cb) => onAuthStateChanged(auth, cb);

/** Czy zalogowany ma prawo zapisu do danych wspolnych. */
export async function czyAdmin(uid) {
  if (!uid) return false;
  try {
    return (await getDoc(doc(db, "admins", uid))).exists();
  } catch {
    return false;
  }
}

const sciezkaUzytkownika = (uid, kolekcja) => collection(db, "users", uid, kolekcja);

export async function wczytaj(uid, kolekcja) {
  const snap = await getDocs(sciezkaUzytkownika(uid, kolekcja));
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}

export async function zapisz(uid, kolekcja, id, dane) {
  await setDoc(doc(db, "users", uid, kolekcja, id), dane);
}

export async function usun(uid, kolekcja, id) {
  await deleteDoc(doc(db, "users", uid, kolekcja, id));
}

/** Ceny wpisane recznie - wspolne dla wszystkich, zapis tylko dla admina. */
export async function wczytajCeny() {
  const snap = await getDocs(collection(db, "price_entries"));
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}

export async function zapiszCeny(id, dane) {
  await setDoc(doc(db, "price_entries", id), dane);
}

export async function usunCeny(id) {
  await deleteDoc(doc(db, "price_entries", id));
}

/** Korekty cen. Nigdy nie nadpisuja ceny zrodlowej - leza obok niej. */
export async function wczytajKorekty() {
  const snap = await getDocs(collection(db, "overrides"));
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}

export async function zapiszKorekte(id, dane) {
  await setDoc(doc(db, "overrides", id), dane);
}

export async function usunKorekte(id) {
  await deleteDoc(doc(db, "overrides", id));
}
