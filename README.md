# DayOne Fitness

Workout planner and tracker built with Streamlit. Workout plans, workout history, exercise data, body weight, calorie entries, height, and favorite exercise are stored in Supabase PostgreSQL.

## Supabase setup

1. Create a Supabase project.
2. Open the Supabase SQL Editor and run [`supabase/migrations/202610070001_dayone_schema.sql`](supabase/migrations/202610070001_dayone_schema.sql). This creates the tables, indexes, auth profile trigger, transactional write functions, and Row Level Security policies.
3. In Supabase **Project Settings → API**, copy the project URL and the publishable/anon key. Do not use a `service_role` key in this app.
4. Copy `.env.example` to `.env` and replace the placeholders:

   ```text
   SUPABASE_URL=https://your-project-ref.supabase.co
   SUPABASE_ANON_KEY=your-publishable-or-anon-key
   ```

   `.env` is ignored by Git. In deployment, set the same values as environment variables instead.
5. Install dependencies with `pip install -r requirements.txt`, then run `streamlit run app.py`.
6. Create an account in the app, or sign in to an existing Supabase Auth account. Supabase email confirmation settings apply to new accounts. The app requires authentication; RLS scopes personal rows to the signed-in user.
7. Use **Import existing local data** in the sidebar to import `data/exercises.csv` and, when present, `data/routine.json` and `data/progress.json`. Imports are tracked per user and source-file content, and repeat imports skip already imported content. Original files are preserved as backups.

The app uses the Supabase publishable/anon key with the signed-in user's Auth token. PostgreSQL RLS policies protect profiles and tracking records. Shared exercise catalog rows can be read by signed-in users; each user's imported or newly created exercises are private. Never expose a service-role secret in Streamlit, browser-facing code, or source control.

## Local data backups

The original CSV and any JSON files in `data/` are retained. Supabase becomes the live persistence store after setup. Migration is explicit and user-scoped: log into the account that should own the imported records, then run the sidebar import. Keep separate backups of these files before removing or changing local copies.
