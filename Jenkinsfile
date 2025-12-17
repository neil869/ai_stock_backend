pipeline {
    agent any

    environment {
        APP_PORT = '8001'
        IMAGE_NAME = 'ai-stock-backend'
        COMPOSE_FILE = 'docker-compose.prod.yml'
    }

    stages {
        stage('Checkout Code') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: '*/main']],
                    doGenerateSubmoduleConfigurations: false,
                    extensions: [],
                    userRemoteConfigs: [[
                        url: 'https://github.com/neil869/ai_stock_backend.git'
                    ]]
                ])
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t ${IMAGE_NAME} .'
            }
        }

        stage('Stop Old Services (if any)') {
            steps {
                script {
                    sh 'docker-compose -f ${COMPOSE_FILE} down || echo "No existing service to stop"'
                }
            }
        }

        stage('Deploy New Service') {
            steps {
                sh 'docker-compose -f ${COMPOSE_FILE} up -d'
            }
        }

        stage('Health Check') {
            steps {
                script {
                    sleep(10)
                    sh 'curl -f http://localhost:${APP_PORT}/docs || exit 1'
                }
            }
        }
    }

    post {
        success {
            echo '✅ CI/CD pipeline succeeded. Service is running on port ${APP_PORT}.'
        }
        failure {
            echo '❌ Build or deployment failed.'
        }
    }
}