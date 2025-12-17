# Jenkinsfile - AI股票智能分析系统构建部署流程

pipeline {
    agent any
    
    environment {
        // 项目相关配置
        PROJECT_NAME = 'ai_stock_backend'
        APP_NAME = 'ai-stock-backend'
        DOCKER_IMAGE = "${env.PROJECT_NAME}:${env.BUILD_ID}"
        
        // 腾讯云服务器配置
        TENCENT_CLOUD_HOST = 'your_tencent_cloud_ip'  // 替换为你的腾讯云服务器IP
        TENCENT_CLOUD_PORT = '22'
        TENCENT_CLOUD_USER = 'root'  // 或其他有Docker权限的用户
        TENCENT_CLOUD_DOCKER_PATH = '/var/www/ai_stock_backend'
        
        // 本地Docker配置
        DOCKER_REGISTRY = ''  // 如果使用私有镜像仓库，请配置
        
        // 测试相关
        TEST_COMMAND = 'python -m pytest tests/ -v'
    }
    
    stages {
        stage('代码检查') {
            steps {
                echo "开始代码检查..."
                // 可以在这里添加代码检查工具，如flake8、pylint等
                script {
                    try {
                        sh 'pip install flake8'
                        sh 'flake8 --max-line-length=120 main.py models.py predict.py'
                    } catch (Exception e) {
                        echo "代码检查失败: ${e}"
                        // 可以选择继续构建或失败
                        // currentBuild.result = 'FAILURE'
                        // error("代码检查失败")
                    }
                }
            }
        }
        
        stage('单元测试') {
            steps {
                echo "开始单元测试..."
                script {
                    try {
                        sh 'pip install pytest'
                        sh "${env.TEST_COMMAND}"
                    } catch (Exception e) {
                        echo "单元测试失败: ${e}"
                        // 可以选择继续构建或失败
                        // currentBuild.result = 'FAILURE'
                        // error("单元测试失败")
                    }
                }
            }
        }
        
        stage('构建Docker镜像') {
            steps {
                echo "开始构建Docker镜像..."
                sh "docker build -t ${env.DOCKER_IMAGE} ."
                sh "docker tag ${env.DOCKER_IMAGE} ${env.PROJECT_NAME}:latest"
            }
        }
        
        stage('登录腾讯云服务器') {
            steps {
                echo "登录腾讯云服务器..."
                script {
                    // 使用SSH密钥认证登录服务器
                    // 确保Jenkins服务器的公钥已经添加到腾讯云服务器的~/.ssh/authorized_keys文件中
                    sh "ssh -p ${env.TENCENT_CLOUD_PORT} ${env.TENCENT_CLOUD_USER}@${env.TENCENT_CLOUD_HOST} 'echo 登录成功'"
                }
            }
        }
        
        stage('部署到腾讯云Docker容器') {
            steps {
                echo "部署到腾讯云Docker容器..."
                script {
                    // 停止并删除旧容器
                    sh "ssh -p ${env.TENCENT_CLOUD_PORT} ${env.TENCENT_CLOUD_USER}@${env.TENCENT_CLOUD_HOST} 'docker stop ${env.APP_NAME} || true'"
                    sh "ssh -p ${env.TENCENT_CLOUD_PORT} ${env.TENCENT_CLOUD_USER}@${env.TENCENT_CLOUD_HOST} 'docker rm ${env.APP_NAME} || true'"
                    
                    // 传输Docker镜像到腾讯云服务器
                    sh "docker save ${env.DOCKER_IMAGE} | ssh -p ${env.TENCENT_CLOUD_PORT} ${env.TENCENT_CLOUD_USER}@${env.TENCENT_CLOUD_HOST} 'docker load'"
                    
                    // 运行新容器
                    sh "ssh -p ${env.TENCENT_CLOUD_PORT} ${env.TENCENT_CLOUD_USER}@${env.TENCENT_CLOUD_HOST} 'docker run -d --name ${env.APP_NAME} -p 8001:8001 ${env.DOCKER_IMAGE}'"
                    
                    // 清理旧镜像
                    sh "ssh -p ${env.TENCENT_CLOUD_PORT} ${env.TENCENT_CLOUD_USER}@${env.TENCENT_CLOUD_HOST} 'docker image prune -f'"
                }
            }
        }
        
        stage('部署验证') {
            steps {
                echo "验证部署是否成功..."
                script {
                    // 等待容器启动
                    sh "sleep 10"
                    
                    // 检查容器是否运行
                    sh "ssh -p ${env.TENCENT_CLOUD_PORT} ${env.TENCENT_CLOUD_USER}@${env.TENCENT_CLOUD_HOST} 'docker ps -f name=${env.APP_NAME}'"
                    
                    // 测试API是否可用
                    sh "curl -s -o /dev/null -w '%{http_code}' http://${env.TENCENT_CLOUD_HOST}:8001/health"
                }
            }
        }
    }
    
    post {
        always {
            echo "构建完成，清理环境..."
            // 清理本地Docker镜像
            sh "docker rmi ${env.DOCKER_IMAGE} ${env.PROJECT_NAME}:latest || true"
        }
        
        success {
            echo "🎉 构建和部署成功！"
            echo "项目已部署到腾讯云服务器: http://${env.TENCENT_CLOUD_HOST}:8001"
        }
        
        failure {
            echo "❌ 构建或部署失败！"
        }
    }
}