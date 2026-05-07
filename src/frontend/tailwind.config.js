/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: {
          light: '#f9f9f9',
          dark: '#1a1a1a',
        },
        surface: {
          light: '#ffffff',
          dark: '#242424',
        },
        border: {
          light: '#e5e5e5',
          dark: '#333333',
        },
        primary: {
          DEFAULT: '#ff4500',
          light: '#ff6b3d',
          dark: '#cc3700',
        },
        youtube: {
          red: '#ff0000',
          dark: '#282828',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        'xl': '12px',
        '2xl': '16px',
      }
    },
  },
  plugins: [],
}
