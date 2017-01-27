#!groovy

def deployDatabaseMigrations(cfEnv) {
  waitUntil {
    try {
      lock(cfEnv) {
        withCredentials([
          string(credentialsId: 'paas_username', variable: 'CF_USERNAME'),
          string(credentialsId: 'paas_password', variable: 'CF_PASSWORD')
        ]) {
          withEnv(["CF_SPACE=${cfEnv}"]) {
            sh 'make cf-deploy-api-db-migration-with-docker'
          }
        }
      }
      true
    } catch(err) {
      echo "Deployment to ${cfEnv} failed: ${err}"
      try {
        slackSend channel: '#govuk-notify', message: "Deployment to ${cfEnv} failed. Please retry or abort: <${env.BUILD_URL}|${env.JOB_NAME} - #${env.BUILD_NUMBER}>", color: 'danger'
      } catch(err2) {
        echo "Sending Slack message failed: ${err2}"
      }
      input "Stage failed. Retry?"
      false
    }
  }
}

def deploy(cfEnv) {
  waitUntil {
    try {
      lock(cfEnv) {
        withCredentials([
          string(credentialsId: 'paas_username', variable: 'CF_USERNAME'),
          string(credentialsId: 'paas_password', variable: 'CF_PASSWORD')
        ]) {
          withEnv(["CF_SPACE=${cfEnv}"]) {
            parallel deployApi: {
              retry(3) {
                sh 'make cf-deploy-api-with-docker'
              }
            }, deployDeliveryCeleryBeat: {
              sleep(10)
              withEnv(["CF_APP=notify-delivery-celery-beat"]) {
                retry(3) {
                  sh 'make cf-deploy-delivery-with-docker'
                }
              }
            }, deployDeliveryWorker: {
              sleep(20)
              withEnv(["CF_APP=notify-delivery-worker"]) {
                retry(3) {
                  sh 'make cf-deploy-delivery-with-docker'
                }
              }
            }, deployDeliveryWorkerSender: {
              sleep(30)
              withEnv(["CF_APP=notify-delivery-worker-sender"]) {
                retry(3) {
                  sh 'make cf-deploy-delivery-with-docker'
                }
              }
            }, deployDeliveryWorkerDatabase: {
              sleep(40)
              withEnv(["CF_APP=notify-delivery-worker-database"]) {
                retry(3) {
                  sh 'make cf-deploy-delivery-with-docker'
                }
              }
            }, deployDeliveryWorkerResearch: {
              sleep(50)
              withEnv(["CF_APP=notify-delivery-worker-research"]) {
                retry(3) {
                  sh 'make cf-deploy-delivery-with-docker'
                }
              }
            }
          }
        }
        gitCommit = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
        sh("git tag -f deployed-to-cf-${cfEnv} ${gitCommit}")
        sh("git push -f origin deployed-to-cf-${cfEnv}")
      }
      true
    } catch(err) {
      echo "Deployment to ${cfEnv} failed: ${err}"
      try {
        slackSend channel: '#govuk-notify', message: "Deployment to ${cfEnv} failed. Please retry or abort: <${env.BUILD_URL}|${env.JOB_NAME} - #${env.BUILD_NUMBER}>", color: 'danger'
      } catch(err2) {
        echo "Sending Slack message failed: ${err2}"
      }
      input "Stage failed. Retry?"
      false
    }
  }
}

def buildJobWithRetry(jobName) {
  waitUntil {
    try {
      build job: jobName
      true
    } catch(err) {
      echo "${jobName} failed: ${err}"
      try {
        slackSend channel: '#govuk-notify', message: "${jobName} failed. Please retry or abort: <${env.BUILD_URL}|${env.JOB_NAME} - #${env.BUILD_NUMBER}>", color: 'danger'
      } catch(err2) {
        echo "Sending Slack message failed: ${err2}"
      }
      input "${jobName} failed. Retry?"
      false
    }
  }
}

try {
  node {
    stage('Build') {
      git url: 'git@github.com:alphagov/notifications-api.git', branch: 'master', credentialsId: 'github_com_and_gds'
      checkout scm

      milestone 10
      withEnv(["PIP_ACCEL_CACHE=${env.JENKINS_HOME}/cache/pip-accel"]) {
        sh 'make cf-build-with-docker'
      }

      stash name: 'source', excludes: 'venv/**,wheelhouse/**', useDefaultExcludes: false
    }

    stage('Test') {
      milestone 20
      sh 'make test-with-docker'

      try {
        junit 'test_results.xml'
      } catch(err) {
        echo "Collecting jUnit results failed: ${err}"
      }

      try {
        withCredentials([string(credentialsId: 'coveralls_repo_token_api', variable: 'COVERALLS_REPO_TOKEN')]) {
          sh 'make coverage-with-docker'
        }
      } catch(err) {
        echo "Coverage failed: ${err}"
      }
    }

    stage('Preview') {
      if (deployToPreview == "true") {
        milestone 30
        deployDatabaseMigrations 'preview'
        buildJobWithRetry 'notify-functional-tests-preview'
        deploy 'preview'
      } else {
        echo 'Preview skipped.'
      }
    }

    stage('Preview tests') {
      if (deployToPreview == "true") {
        buildJobWithRetry 'notify-functional-tests-preview'
        buildJobWithRetry 'run-ruby-client-integration-tests'
        buildJobWithRetry 'run-python-client-integration-tests'
        buildJobWithRetry 'run-net-client-integration-tests'
        buildJobWithRetry 'run-node-client-integration-tests'
        buildJobWithRetry 'run-java-client-integration-tests'
        buildJobWithRetry 'run-php-client-integration-tests'
      } else {
        echo 'Preview tests skipped.'
      }
    }
  }

  stage('Staging') {
    if (deployToStaging == "true") {
      input 'Approve?'
      milestone 40
      node {
        unstash 'source'
        deployDatabaseMigrations 'staging'
        buildJobWithRetry 'notify-functional-tests-staging'
        deploy 'staging'
      }
    } else {
      echo 'Staging skipped.'
    }
  }

  stage('Staging tests') {
    if (deployToStaging == "true") {
      buildJobWithRetry 'notify-functional-tests-staging'
      buildJobWithRetry 'notify-functional-provider-tests-staging'
    } else {
      echo 'Staging tests skipped'
    }
  }

  stage('Prod') {
    if (deployToProduction == "true") {
      input 'Approve?'
      milestone 50
      node {
        unstash 'source'
        deployDatabaseMigrations 'production'
        buildJobWithRetry 'notify-functional-admin-tests-production'
        buildJobWithRetry 'notify-functional-api-email-test-production'
        buildJobWithRetry 'notify-functional-api-sms-test-production'
        deploy 'production'
      }
    } else {
      echo 'Production skipped.'
    }
  }

  stage('Prod tests') {
    if (deployToProduction == "true") {
      buildJobWithRetry 'notify-functional-admin-tests-production'
      buildJobWithRetry 'notify-functional-api-email-test-production'
      buildJobWithRetry 'notify-functional-api-sms-test-production'
      buildJobWithRetry 'notify-functional-provider-email-test-production'
      buildJobWithRetry 'notify-functional-provider-sms-test-production'
    } else {
      echo 'Production tests skipped.'
    }
  }
} catch (org.jenkinsci.plugins.workflow.steps.FlowInterruptedException fie) {
  currentBuild.result = 'ABORTED'
} catch (err) {
  currentBuild.result = 'FAILURE'
  echo "Pipeline failed: ${err}"
  slackSend channel: '#govuk-notify', message: "${env.JOB_NAME} - #${env.BUILD_NUMBER} failed (<${env.BUILD_URL}|Open>)", color: 'danger'
} finally {
  node {
    try {
      step([$class: 'Mailer', notifyEveryUnstableBuild: true, recipients: 'notify-support+jenkins@digital.cabinet-office.gov.uk', sendToIndividuals: false])
    } catch(err) {
      echo "Sending email failed: ${err}"
    }

    try {
      sh 'make clean-docker-containers'
    } catch(err) {
      echo "Cleaning up Docker containers failed: ${err}"
    }
  }
}
