-- Migration: Add mnemonic fields to question table
-- Run this in Supabase SQL Editor

-- Add mnemonic columns
ALTER TABLE question 
ADD COLUMN IF NOT EXISTS mnemonic_enabled BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS mnemonic_acronym VARCHAR(20),
ADD COLUMN IF NOT EXISTS mnemonic_expansion TEXT,
ADD COLUMN IF NOT EXISTS mnemonic_teaching_context TEXT;

-- Create index for filtering questions with mnemonics
CREATE INDEX IF NOT EXISTS idx_question_mnemonic_enabled 
ON question(mnemonic_enabled);

-- Add comment for documentation
COMMENT ON COLUMN question.mnemonic_enabled IS 'Whether this question has a mnemonic hint available';
COMMENT ON COLUMN question.mnemonic_acronym IS 'Short acronym shown when hint is revealed (e.g., OPQRST)';
COMMENT ON COLUMN question.mnemonic_expansion IS 'Full mnemonic expansion shown after wrong answers';
COMMENT ON COLUMN question.mnemonic_teaching_context IS 'Why this mnemonic applies to this specific question';
