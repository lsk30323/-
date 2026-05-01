import 'server-only';
import { drizzle } from 'drizzle-orm/libsql';
import { createClient, type Client } from '@libsql/client';
import * as schema from './schema';

declare global {
  var __libsqlClient: Client | undefined;
}

const client =
  globalThis.__libsqlClient ??
  createClient({
    url: process.env.TURSO_DATABASE_URL ?? 'file:./db/local.db',
    authToken: process.env.TURSO_AUTH_TOKEN,
  });

if (process.env.NODE_ENV !== 'production') {
  globalThis.__libsqlClient = client;
}

export const db = drizzle(client, { schema });
export { schema };
