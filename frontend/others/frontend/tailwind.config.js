/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#7C3AED',      // violet foncé
        secondary: '#93C5FD',    // bleu clair
        assistant: '#D3E8FF',    // bulle assistant
        user: '#E5D2FF',         // bulle utilisateur
        success: '#10B981',
        warning: '#FBBF24',
        danger: '#EF4444',
        info: '#3B82F6'
      }
    }
  },
  plugins: []
}