<script setup lang="ts">
import { Activity, LayoutDashboard, Database, History, UserRound, Thermometer, Droplets, Sun, Lightbulb, Fan, Waves, BellRing, Search, Filter, RotateCcw, ChevronLeft, ChevronRight, ChevronDown, ArrowUpDown, ExternalLink, Github, FileText, Send, Figma, Menu, X, Wifi, Check, Mail, GraduationCap, Cpu, RefreshCw, CalendarDays } from 'lucide-vue-next'
defineProps<{ name: string; size?: number }>()
const icons: Record<string, unknown> = { activity: Activity, dashboard: LayoutDashboard, data: Database, history: History, profile: UserRound, temperature: Thermometer, humidity: Droplets, light: Sun, bulb: Lightbulb, fan: Fan, pump: Waves, buzzer: BellRing, search: Search, filter: Filter, reset: RotateCcw, left: ChevronLeft, right: ChevronRight, down: ChevronDown, sort: ArrowUpDown, external: ExternalLink, github: Github, file: FileText, send: Send, figma: Figma, menu: Menu, close: X, wifi: Wifi, check: Check, mail: Mail, graduation: GraduationCap, cpu: Cpu, refresh: RefreshCw, calendar: CalendarDays }
</script>
<template><component :is="icons[name] || Activity" :size="size || 20" :stroke-width="1.8" aria-hidden="true" /></template>
