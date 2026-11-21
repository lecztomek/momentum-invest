/**
 * Testy regul Firestore na emulatorze.
 *
 * Pomylka w jednej linijce regul wystawia salda na swiat, a baza tego nie
 * zglosi - nikt sie nie dowie, ze ktos czyta cudze dane. Dlatego kazda
 * sciezka ma tu test zarowno na to, co ma dzialac, jak i na to, co ma byc
 * zablokowane.
 *
 *   node --test firebase/tests/rules.test.mjs     (przy dzialajacym emulatorze)
 */
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import {
  initializeTestEnvironment,
  assertSucceeds,
  assertFails,
} from "@firebase/rules-unit-testing";
import { doc, getDoc, setDoc, deleteDoc, updateDoc } from "firebase/firestore";

const env = await initializeTestEnvironment({
  projectId: "test-regul",
  firestore: {
    rules: readFileSync("firebase/firestore.rules", "utf8"),
    host: "127.0.0.1",
    port: 8080,
  },
});

// admin jest nadawany z konsoli, wiec w testach wstawiamy go z pominieciem regul
await env.withSecurityRulesDisabled(async (ctx) => {
  await setDoc(doc(ctx.firestore(), "admins/szef"), { od: "konsola" });
});

const nikt = () => env.unauthenticatedContext().firestore();
const szef = () => env.authenticatedContext("szef").firestore();
const ala = () => env.authenticatedContext("ala").firestore();
const bob = () => env.authenticatedContext("bob").firestore();

test.after(() => env.cleanup());

test("niezalogowany nie widzi niczego", async () => {
  await assertFails(getDoc(doc(nikt(), "price_entries/10_2026-12-10")));
  await assertFails(getDoc(doc(nikt(), "users/ala")));
  await assertFails(setDoc(doc(nikt(), "price_entries/10_2026-12-10"), { px: {} }));
});

test("zalogowany czyta ceny, ale ich nie zapisuje", async () => {
  await assertSucceeds(getDoc(doc(ala(), "price_entries/10_2026-12-10")));
  await assertFails(setDoc(doc(ala(), "price_entries/10_2026-12-10"), { px: { XLK: 1 } }));
});

test("admin zapisuje ceny", async () => {
  await assertSucceeds(
    setDoc(doc(szef(), "price_entries/10_2026-12-10"), { tranche: 10, px: { XLK: 285.4 } }),
  );
});

test("kursy walut: czyta kazdy zalogowany, pisze tylko admin", async () => {
  await assertFails(getDoc(doc(nikt(), "fx_rates/2026-03-10")));
  await assertSucceeds(getDoc(doc(ala(), "fx_rates/2026-03-10")));
  await assertFails(setDoc(doc(ala(), "fx_rates/2026-03-10"), { d: "2026-03-10", k: 4.2 }));
  await assertSucceeds(setDoc(doc(szef(), "fx_rates/2026-03-10"), { d: "2026-03-10", k: 4.2 }));
  await assertSucceeds(deleteDoc(doc(szef(), "fx_rates/2026-03-10")));
});

test("korekta wymaga powodu i autora, i nie da sie jej podmienic", async () => {
  await assertFails(setDoc(doc(szef(), "overrides/10_2026-12-10_XLK"), { value: 1 }));
  await assertSucceeds(
    setDoc(doc(szef(), "overrides/10_2026-12-10_XLK"), {
      value: 1, reason: "zly kurs z feedu", author: "szef",
    }),
  );
  await assertFails(updateDoc(doc(szef(), "overrides/10_2026-12-10_XLK"), { value: 2 }));
  await assertSucceeds(deleteDoc(doc(szef(), "overrides/10_2026-12-10_XLK")));
});

test("uzytkownik rzadzi wylacznie swoimi danymi", async () => {
  await assertSucceeds(setDoc(doc(ala(), "users/ala"), { podzial: 0.5 }));
  await assertSucceeds(setDoc(doc(ala(), "users/ala/transactions/t1"), { kwota: 1000 }));
  await assertSucceeds(getDoc(doc(ala(), "users/ala/transactions/t1")));
});

test("cudzych danych nie widzi nikt, z adminem wlacznie", async () => {
  await assertFails(getDoc(doc(bob(), "users/ala")));
  await assertFails(getDoc(doc(bob(), "users/ala/transactions/t1")));
  await assertFails(setDoc(doc(bob(), "users/ala/transactions/t2"), { kwota: 1 }));
  await assertFails(getDoc(doc(szef(), "users/ala/transactions/t1")));
});

test("nikt nie dopisze sie do adminow", async () => {
  await assertFails(setDoc(doc(ala(), "admins/ala"), {}));
  await assertFails(setDoc(doc(szef(), "admins/ala"), {}));
  await assertFails(deleteDoc(doc(szef(), "admins/szef")));
});

test("kolekcja spoza schematu jest zamknieta", async () => {
  await assertFails(getDoc(doc(ala(), "cokolwiek/x")));
  await assertFails(setDoc(doc(szef(), "cokolwiek/x"), { a: 1 }));
});
