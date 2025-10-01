-- Initial database schema for Telegram Cover Letter Bot

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);

-- User profiles (resumes)
CREATE TABLE IF NOT EXISTS user_profiles (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    cv_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

CREATE INDEX idx_user_profiles_telegram_id ON user_profiles(telegram_id);

-- Sent vacancies (для отслеживания уже отправленных откликов)
CREATE TABLE IF NOT EXISTS sent_vacancies (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    vacancy_id VARCHAR(50) NOT NULL,
    vacancy_name TEXT,
    employer_name TEXT,
    score DECIMAL(5,3),
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(telegram_id, vacancy_id),
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

CREATE INDEX idx_sent_vacancies_telegram_id ON sent_vacancies(telegram_id);
CREATE INDEX idx_sent_vacancies_sent_at ON sent_vacancies(sent_at);

-- HH.ru OAuth tokens table (для хранения токенов авторизации)
CREATE TABLE IF NOT EXISTS hh_oauth_tokens (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_type VARCHAR(50) DEFAULT 'Bearer',
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

CREATE INDEX idx_hh_oauth_tokens_telegram_id ON hh_oauth_tokens(telegram_id);
CREATE INDEX idx_hh_oauth_tokens_expires_at ON hh_oauth_tokens(expires_at);

-- HH.ru user resumes (список резюме пользователя на HH.ru)
CREATE TABLE IF NOT EXISTS hh_user_resumes (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    resume_id VARCHAR(100) NOT NULL,
    resume_title TEXT,
    is_active BOOLEAN DEFAULT true,
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(telegram_id, resume_id),
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

CREATE INDEX idx_hh_user_resumes_telegram_id ON hh_user_resumes(telegram_id);
CREATE INDEX idx_hh_user_resumes_is_default ON hh_user_resumes(telegram_id, is_default);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_profiles_updated_at BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_hh_oauth_tokens_updated_at BEFORE UPDATE ON hh_oauth_tokens
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_hh_user_resumes_updated_at BEFORE UPDATE ON hh_user_resumes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
