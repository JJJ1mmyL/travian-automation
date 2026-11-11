from travian.automations import adventure, build, farm_list, tasks

AUTOMATIONS = {
    farm_list.name: farm_list,
    build.name: build,
    adventure.name: adventure,
    tasks.name: tasks,
}
