// src/utils/tableStore.js
import localforage from 'localforage';

export const tableStore = localforage.createInstance({
  name: 'chat_tables_v1',      // nom de “base”
});

// Sauvegarde asynchrone
export async function saveTable(key, rows) {
  await tableStore.setItem(key, rows);
}

// Lecture asynchrone
export async function loadTable(key) {
  return tableStore.getItem(key);
}
