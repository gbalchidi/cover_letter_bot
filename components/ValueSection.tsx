'use client'

import { motion } from 'framer-motion'
import { Zap, Shield, Clock, Target, Users, TrendingUp } from 'lucide-react'

export default function ValueSection() {
  const features = [
    {
      icon: Zap,
      title: "Мгновенный анализ",
      description: "AI анализирует ваше резюме и вакансию за секунды, выявляя ключевые совпадения",
      color: "from-blue-500 to-cyan-500"
    },
    {
      icon: Shield,
      title: "Персонализация",
      description: "Каждое сопроводительное письмо уникально и адаптировано под конкретную вакансию",
      color: "from-green-500 to-emerald-500"
    },
    {
      icon: Clock,
      title: "Экономия времени",
      description: "Создавайте профессиональные письма за минуты вместо часов ручной работы",
      color: "from-purple-500 to-pink-500"
    },
    {
      icon: Target,
      title: "Точность попадания",
      description: "Повышайте шансы на отклик благодаря точному соответствию требованиям",
      color: "from-orange-500 to-red-500"
    },
    {
      icon: Users,
      title: "Простота использования",
      description: "Интуитивный интерфейс в Telegram - никаких сложных форм или регистраций",
      color: "from-indigo-500 to-blue-500"
    },
    {
      icon: TrendingUp,
      title: "Постоянное улучшение",
      description: "AI учится на ваших успехах и адаптирует стратегии для лучших результатов",
      color: "from-teal-500 to-green-500"
    }
  ]

  return (
    <section className="py-20 bg-gradient-to-b from-dark-900 to-dark-800">
      <div className="container-custom">
        {/* Section Header */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-bold mb-6">
            <span className="text-white">Почему наш бот</span>
            <br />
            <span className="gradient-text">лучше других?</span>
          </h2>
          <p className="text-xl text-gray-300 max-w-3xl mx-auto">
            Мы объединили передовые технологии AI с глубоким пониманием HR-процессов, 
            чтобы дать вам неоспоримое преимущество на рынке труда
          </p>
        </motion.div>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {features.map((feature, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: index * 0.1 }}
              className="group"
            >
              <div className="bg-dark-800/50 backdrop-blur-sm rounded-2xl p-8 border border-gray-800/50 hover:border-gray-700/50 transition-all duration-300 hover:shadow-2xl hover:shadow-primary-500/10">
                {/* Icon */}
                <div className={`w-16 h-16 bg-gradient-to-r ${feature.color} rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300`}>
                  <feature.icon className="w-8 h-8 text-white" />
                </div>
                
                {/* Content */}
                <h3 className="text-xl font-semibold text-white mb-4 group-hover:text-primary-400 transition-colors">
                  {feature.title}
                </h3>
                <p className="text-gray-400 leading-relaxed">
                  {feature.description}
                </p>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Bottom CTA */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, delay: 0.4 }}
          className="text-center mt-16"
        >
          <div className="bg-gradient-to-r from-primary-900/20 to-secondary-900/20 rounded-3xl p-8 border border-primary-500/20">
            <h3 className="text-2xl font-bold text-white mb-4">
              Готовы получить преимущество?
            </h3>
            <p className="text-gray-300 mb-6">
              Присоединяйтесь к тысячам успешных кандидатов, которые уже используют наш бот
            </p>
            <button className="btn-primary text-lg px-8 py-4">
              Начать бесплатно
            </button>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
