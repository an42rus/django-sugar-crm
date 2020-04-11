from __future__ import print_function, unicode_literals
from sugarcrm import Task

# This is the URL for the v4 REST API in your SugarCRM server.
# url = ''
# username = ''
# password = ''

# This way you log-in to your SugarCRM instance.
# conn = Sugarcrm(url, username, password)
# TaskModel = Task(conn)


# Examples for Django
# You need to put connection settings to the Django settings file first.
# SUGAR_CRM_URL = <sugarcrm api url>
# SUGAR_CRM_USERNAME = <sugarcrm username>
# SUGAR_CRM_PASSWORD = <sugarcrm password>

# creation of new Tasks
new_task = Task(**{'name': 'test'})
new_task.save()

# change field value
TaskModel = Task()
task = TaskModel.objects.get(pk=new_task.id)
old_name = task.name
print('before change', task.name)
task['name'] = 'New Name'
print('before save', task.name)
task.save()

# revert field value
query = TaskModel.objects.filter(id=new_task.id).only('id', 'name', 'date_start').order_by('date_start')
task = query.first()
print('after save', task.name)
task['name'] = old_name
task.save()
query = TaskModel.objects.filter(id=new_task.id).only('id', 'name', 'date_start').order_by('date_start')
task = query.first()
print('after revert', task.name)
task.delete()

query = TaskModel.objects.filter(name=new_task.name).order_by('date_start')
task = query.first()
print('check after delete', task)


