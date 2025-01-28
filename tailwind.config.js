/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html', // Adjust this path to match your template folder
    './static/**/*.js',      // Include any JS files with Tailwind classes
  ],
  theme: {
      extend: {}, // Extend or customize your theme here
  },
  plugins: [],
}

