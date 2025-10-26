-- V4__add_template_ver.sql
-- Adds nullable template_ver for apps that version task templates.
-- Safe to run multiple times.
ALTER TABLE IF EXISTS public.tasks
  ADD COLUMN IF NOT EXISTS template_ver integer;
