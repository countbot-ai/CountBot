# FileSelector Component

A reusable file selector component with preview, validation, and multi-file support.

## Features

- ✅ File selection with native file dialog
- ✅ Multiple file support
- ✅ File size validation
- ✅ Maximum files count validation
- ✅ Image preview for image files
- ✅ File type filtering (accept attribute)
- ✅ Remove individual files
- ✅ Clear all files
- ✅ Disabled state
- ✅ Internationalization support
- ✅ Accessible (keyboard navigation, ARIA labels)

## Usage

### Basic Usage

```vue
<template>
  <FileSelector
    @change="handleFilesChange"
    @error="handleFileError"
  />
</template>

<script setup lang="ts">
import { FileSelector } from '@/components/ui'

const handleFilesChange = (files: File[]) => {
  console.log('Selected files:', files)
}

const handleFileError = (message: string) => {
  console.error('File error:', message)
}
</script>
```

### With Custom Configuration

```vue
<template>
  <FileSelector
    :multiple="true"
    :max-size="5 * 1024 * 1024"
    :max-files="3"
    accept="image/*"
    :disabled="isUploading"
    :show-preview="true"
    @change="handleFilesChange"
    @error="handleFileError"
  />
</template>
```

### Single File Mode

```vue
<template>
  <FileSelector
    :multiple="false"
    accept=".pdf,.doc,.docx"
    @change="handleFilesChange"
  />
</template>
```

### With Ref (Programmatic Control)

```vue
<template>
  <FileSelector
    ref="fileSelectorRef"
    @change="handleFilesChange"
  />
  <button @click="clearFiles">Clear All</button>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { FileSelector } from '@/components/ui'

const fileSelectorRef = ref<InstanceType<typeof FileSelector>>()

const clearFiles = () => {
  fileSelectorRef.value?.clearFiles()
}

const getFiles = () => {
  return fileSelectorRef.value?.getFiles() || []
}
</script>
```

## Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `accept` | `string` | `'*/*'` | File types to accept (e.g., 'image/*', '.pdf,.doc') |
| `multiple` | `boolean` | `true` | Allow multiple file selection |
| `maxSize` | `number` | `10485760` | Maximum file size in bytes (default: 10MB) |
| `maxFiles` | `number` | `5` | Maximum number of files |
| `disabled` | `boolean` | `false` | Disable the file selector |
| `title` | `string` | - | Custom tooltip text |
| `size` | `number` | `20` | Icon size in pixels |
| `showPreview` | `boolean` | `true` | Show file preview |

## Events

| Event | Payload | Description |
|-------|---------|-------------|
| `change` | `File[]` | Emitted when files are selected or removed |
| `error` | `string` | Emitted when validation fails |

## Exposed Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `clearFiles` | - | `void` | Clear all selected files |
| `getFiles` | - | `File[]` | Get currently selected files |

## Validation

The component performs the following validations:

1. **File Count**: Ensures the total number of files doesn't exceed `maxFiles`
2. **File Size**: Ensures each file doesn't exceed `maxSize`
3. **Single File Mode**: Ensures only one file is selected when `multiple` is `false`

When validation fails, the `error` event is emitted with a localized error message.

## Internationalization

The component uses the following i18n keys:

- `chat.attachFile` - Button tooltip
- `chat.fileSelectorSingleOnly` - Error when multiple files selected in single mode
- `chat.fileSelectorMaxFiles` - Error when max files exceeded
- `chat.fileSelectorMaxSize` - Error when file size exceeded
- `common.remove` - Remove button tooltip

## Styling

The component uses CSS variables for theming:

- `--bg-primary` - Background color
- `--bg-secondary` - Secondary background color
- `--border-color` - Border color
- `--text-primary` - Primary text color
- `--text-secondary` - Secondary text color
- `--text-tertiary` - Tertiary text color
- `--hover-bg` - Hover background color
- `--color-primary` - Primary color
- `--color-error` - Error color
- `--color-error-alpha` - Error color with alpha
- `--radius-sm` - Small border radius
- `--radius-md` - Medium border radius
- `--spacing-xs` - Extra small spacing
- `--spacing-sm` - Small spacing
- `--spacing-md` - Medium spacing
- `--font-size-xs` - Extra small font size
- `--font-size-sm` - Small font size
- `--font-weight-medium` - Medium font weight
- `--transition-base` - Base transition

## Accessibility

- Keyboard accessible (button can be focused and activated with Enter/Space)
- ARIA labels for screen readers
- Proper focus management
- Semantic HTML

## Browser Support

- Modern browsers with File API support
- Image preview requires URL.createObjectURL support

## Notes

- Image previews are automatically generated for files with `image/*` MIME type
- Preview URLs are automatically revoked when files are removed to prevent memory leaks
- The file input is hidden and triggered programmatically for better styling control
