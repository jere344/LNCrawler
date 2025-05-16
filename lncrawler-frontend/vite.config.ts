import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@assets': path.resolve(__dirname, './src/assets'),
      '@components': path.resolve(__dirname, './src/components'),
      '@models': path.resolve(__dirname, './src/models'),
      '@services': path.resolve(__dirname, './src/services'),
      '@theme': path.resolve(__dirname, './src/theme'),
      '@config': path.resolve(__dirname, './src/config'),
      '@utils': path.resolve(__dirname, './src/utils'),
    }
  },
  build: {
    // Output directory
    outDir: 'dist',
    
    // Ensure JavaScript files are properly emitted with correct types
    assetsDir: 'assets',
    
    // Configure rollup options
    rollupOptions: {
      output: {
        // Ensure proper file extensions and MIME types
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
    
    // Minify options
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: false, // Keep console logs for debugging
        drop_debugger: true,
      },
    },
    
    // Sourcemaps for easier debugging
    sourcemap: true,
  },
  // Server options
  server: {
    host: true,
    port: 8185,
    // Use consistent content types
    fs: {
      strict: true,
    },
  },
})
