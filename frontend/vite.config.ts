import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { resolve } from 'node:path'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [
        vue({
            script: {
                defineModel: true,
                propsDestructure: true
            }
        })
    ],

    resolve: {
        alias: {
            '@': fileURLToPath(new URL('./src', import.meta.url)),
            '@components': fileURLToPath(new URL('./src/components', import.meta.url)),
            '@modules': fileURLToPath(new URL('./src/modules', import.meta.url)),
            '@store': fileURLToPath(new URL('./src/store', import.meta.url)),
            '@api': fileURLToPath(new URL('./src/api', import.meta.url)),
            '@composables': fileURLToPath(new URL('./src/composables', import.meta.url)),
            '@i18n': fileURLToPath(new URL('./src/i18n', import.meta.url)),
            '@assets': fileURLToPath(new URL('./src/assets', import.meta.url))
        }
    },

    server: {
        port: 5173,
        strictPort: false,
        host: '127.0.0.1',
        cors: true,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
                secure: false
            },
            '/ws': {
                target: 'ws://127.0.0.1:8000',
                ws: true,
                changeOrigin: true
            }
        }
    },

    build: {
        outDir: 'dist',
        assetsDir: 'assets',
        sourcemap: false,
        minify: 'esbuild',
        target: 'es2015',
        rollupOptions: {
            output: {
                chunkFileNames: 'assets/js/[name]-[hash].js',
                entryFileNames: 'assets/js/[name]-[hash].js',
                assetFileNames: 'assets/[ext]/[name]-[hash].[ext]'
            }
        },
        chunkSizeWarningLimit: 1000,
        reportCompressedSize: false
    },

    optimizeDeps: {
        include: [
            'vue',
            'vue-router',
            'pinia',
            'axios',
            'lucide-vue-next',
            'marked',
            'highlight.js',
            'vue-i18n',
            '@vueuse/core'
        ]
    },

    css: {
        preprocessorOptions: {
            css: {
                charset: false
            }
        },
        devSourcemap: true
    },

    test: {
        globals: true,
        environment: 'jsdom',
        setupFiles: ['./tests/setup.ts'],
        coverage: {
            provider: 'v8',
            reporter: ['text', 'json', 'html'],
            exclude: [
                'node_modules/',
                'tests/',
                '**/*.d.ts',
                '**/*.config.*',
                '**/mockData'
            ]
        }
    },

    define: {
        __APP_VERSION__: JSON.stringify(process.env.npm_package_version || '0.1.0')
    },

    esbuild: {
        drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
        legalComments: 'none',
        treeShaking: true
    },

    // Performance optimizations
    performance: {
        maxEntrypointSize: 512000,
        maxAssetSize: 512000
    }
})
